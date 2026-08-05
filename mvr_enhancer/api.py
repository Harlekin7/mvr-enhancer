"""JS<->Python-Bruecke (pywebview ``js_api``) und Anwendungszustand.

``Api`` ist die einzige Naht zwischen der (spaeteren) Web-UI und dem fertigen
Core: saemtliche oeffentlichen Methoden geben ausnahmslos
``{"ok": True, "data": ...}`` bzw. ``{"ok": False, "error": "<deutscher,
nutzerlesbarer Text>"}`` zurueck und werfen nie ueber die Bruecke hinweg.
``Api._state`` (die Instanzattribute mit ``_``-Praefix) ist die Single
Source of Truth; ``get_state()`` baut daraus bei jedem Aufruf frisch das
komplette, von der UI konsumierte Zustands-Dict.

Lange Operationen (``load_mvr``, ``rescan_library``, ``share_*``,
``run_export``) laufen in Produktion in einem ``threading.Thread`` und
melden sich per ``window.evaluate_js(f"app.onEvent({json})")`` mit Events
``{"type": "state"|"toast"|"progress", ...}`` zurueck. Mit ``Api(sync=True)``
(Testmodus) laeuft dieselbe Arbeit synchron auf dem aufrufenden Thread, und
Events landen statt in ``evaluate_js`` in der Liste ``self.events``.
"""

import json
import logging
import os
import threading
from datetime import datetime

import webview

from mvr_enhancer.core.analysis import (
    aggregate_fixture_types,
    compute_stats,
    detect_address_collisions,
)
from mvr_enhancer.core.enricher import _clean_gdtf_name, enrich_mvr
from mvr_enhancer.core.gdtf import (
    MATCH_THRESHOLD,
    find_all_gdtf_suggestions,
    find_gdtf_file,
    find_matching_gdtf,
    invalidate_gdtf_cache,
    load_gdtf_library,
)
from mvr_enhancer.core.models import (
    Assignment,
    Candidate,
    FixtureType,
    ModeFallbackWarning,
    serialize,
)
from mvr_enhancer.core.mvr_reader import read_mvr
from mvr_enhancer.core.share import GdtfShareClient
from mvr_enhancer.settings import Settings
from mvr_enhancer.winsec import decrypt_password, encrypt_password

log = logging.getLogger(__name__)

_BASE_TITLE = "Groh·PA MVR Export"


def _resolve_initial_mode(existing_mode: str, modes: list[dict]) -> tuple[str, bool]:
    """Bestimmt den initialen GDTF-Modus per Substring-Abgleich, sonst ``modes[0]``.

    Analog zu ``enricher._resolve_mode_name``, aber auf den UI-Kandidaten-
    Dicts (``{"name": str, "channel_count": int}``) statt ``GdtfMode``-
    Dataclasses. Gibt ``(mode_name, confirmed)`` zurueck; ``confirmed=False``
    bedeutet, dass nur der reine Notnagel ``modes[0]`` gegriffen hat.
    """
    existing_lower = (existing_mode or "").lower()
    if existing_lower:
        for mode in modes:
            name_lower = mode["name"].lower()
            if existing_lower in name_lower or name_lower in existing_lower:
                return mode["name"], True
    if modes:
        return modes[0]["name"], False
    return "", False


class Api:
    """pywebview ``js_api``-Objekt: Bruecke zwischen UI und Core-Modulen."""

    def __init__(self, sync: bool = False, base_dir: str | None = None):
        self._sync = sync
        self._window = None
        self.events: list[dict] = []
        self._lock = threading.RLock()

        self._settings = Settings.load(base_dir)
        self._share = GdtfShareClient(
            cache_path=os.path.join(self._settings.base_dir, "share_list_cache.json")
        )

        self._scene = None
        self._types: list[FixtureType] = []
        self._stats = None
        self._candidates: dict[str, list[Candidate]] = {}
        self._assignments: dict[str, Assignment] = {}
        self._mvr_path: str | None = None
        self._file_meta: dict = {}
        self._active_step = 0

        self._grouping = self._settings.group_by_position
        self._library_dir = self._settings.gdtf_library_dir
        self._gdtf_library = (
            load_gdtf_library(self._library_dir) if self._library_dir else {}
        )

        self._warnings = {"fallbacks": [], "collisions": [], "cleanup_preview": None}
        self._export_state = {"done": False, "path": "", "size_mb": 0.0, "time": ""}

        self._auto_login()

    # ──── Fenster-/Event-Wiring ────

    def set_window(self, window) -> None:
        """Verbindet die Api mit dem echten pywebview-Fenster (aus ``main.run()``)."""
        self._window = window

    def _emit(self, event: dict) -> None:
        if self._sync or self._window is None:
            self.events.append(event)
            return
        try:
            self._window.evaluate_js(f"app.onEvent({json.dumps(event)})")
        except Exception:
            log.exception("Event konnte nicht an die UI uebertragen werden")

    def _emit_after(self, result: dict) -> None:
        if result.get("ok"):
            self._emit({"type": "state", "data": self.get_state()["data"]})
        else:
            self._emit(
                {
                    "type": "toast",
                    "level": "error",
                    "message": result.get("error", "Unbekannter Fehler."),
                }
            )

    def _safe_call(self, worker) -> dict:
        try:
            return worker()
        except Exception as e:
            log.exception("Hintergrund-Operation fehlgeschlagen")
            return {"ok": False, "error": f"Unerwarteter Fehler: {e}"}

    def _run_long(self, worker) -> dict:
        """Fuehrt ``worker`` synchron (Testmodus) oder in einem Thread aus."""
        if self._sync:
            result = self._safe_call(worker)
            self._emit_after(result)
            return result

        def _target():
            result = self._safe_call(worker)
            self._emit_after(result)

        threading.Thread(target=_target, daemon=True).start()
        return {"ok": True, "data": {"started": True}}

    # ──── Auto-Login ────

    def _auto_login(self) -> None:
        if not (self._settings.share_user and self._settings.share_password_enc):
            return
        try:
            password = decrypt_password(self._settings.share_password_enc)
        except ValueError:
            return
        if password:
            self._share.login(self._settings.share_user, password)

    # ──── Zustand ────

    def get_state(self) -> dict:
        """Baut den kompletten UI-Zustand aus ``Api``s internem Zustand."""
        try:
            with self._lock:
                types_out = []
                assigned_count = 0
                open_count = 0
                for fixture_type in self._types:
                    assignment = self._assignments.get(fixture_type.key) or Assignment()
                    candidates = self._candidates.get(fixture_type.key, [])
                    types_out.append(
                        {
                            "key": fixture_type.key,
                            "name": fixture_type.name,
                            "count": fixture_type.count,
                            "positions": fixture_type.positions,
                            "meta_line": fixture_type.meta_line,
                            "existing_spec": fixture_type.existing_spec,
                            "existing_mode": fixture_type.existing_mode,
                            "candidates": [serialize(c) for c in candidates],
                            "assignment": serialize(assignment),
                        }
                    )
                    if assignment.removed:
                        continue
                    if assignment.gdtf_name:
                        assigned_count += 1
                    else:
                        open_count += 1

                recent = [
                    {
                        "path": entry["path"],
                        "name": os.path.basename(entry["path"]),
                        "ts": entry["ts"],
                    }
                    for entry in self._settings.recent_files
                ]

                data = {
                    "mvr_loaded": self._scene is not None,
                    "file_meta": self._file_meta,
                    "stats": serialize(self._stats) if self._stats is not None else None,
                    "types": types_out,
                    "grouping": self._grouping,
                    "share": {
                        "logged_in": self._share.logged_in,
                        "user": self._settings.share_user,
                    },
                    "library": {
                        "dir": self._library_dir,
                        "count": len(self._gdtf_library),
                    },
                    "recent": recent,
                    "warnings": self._warnings,
                    "export": {**self._export_state, "default_path": self._default_export_path()},
                    "assigned_count": assigned_count,
                    "open_count": open_count,
                }
            return {"ok": True, "data": data}
        except Exception as e:
            log.exception("get_state fehlgeschlagen")
            return {"ok": False, "error": f"Zustand konnte nicht ermittelt werden: {e}"}

    def _default_export_path(self) -> str:
        if not self._mvr_path:
            return ""
        mvr_dir = os.path.dirname(self._mvr_path)
        stem = os.path.splitext(os.path.basename(self._mvr_path))[0]
        base_dir = self._settings.last_export_dir or mvr_dir
        return os.path.join(base_dir, f"{stem}_MA3.mvr")

    # ──── Hilfsfunktionen ────

    def _type_by_key(self, key: str) -> FixtureType | None:
        for fixture_type in self._types:
            if fixture_type.key == key:
                return fixture_type
        return None

    def _find_candidate(self, type_key: str, gdtf_name: str) -> Candidate | None:
        for candidate in self._candidates.get(type_key, []):
            if candidate.gdtf_name == gdtf_name:
                return candidate
        return None

    def _modes_from_library(self, gdtf_name: str) -> list[dict]:
        fixture = self._gdtf_library.get(gdtf_name)
        if fixture is None:
            return []
        return [{"name": m.name, "channel_count": m.channel_count} for m in fixture.modes]

    def _build_candidates_for_type(self, fixture_type: FixtureType) -> list[Candidate]:
        suggestions = find_all_gdtf_suggestions(
            [fixture_type.name], self._gdtf_library, {}
        )
        matches = suggestions.get(fixture_type.name, [])
        candidates = [
            Candidate(
                gdtf_name=gdtf.name,
                manufacturer=gdtf.manufacturer,
                revision=gdtf.revision,
                score=score,
                modes=[{"name": m.name, "channel_count": m.channel_count} for m in gdtf.modes],
                source="library",
            )
            for gdtf, score in matches
        ]
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    # ──── MVR laden/entfernen ────

    def choose_mvr(self) -> dict:
        try:
            if self._window is None:
                return {"ok": False, "error": "Kein Fenster verfuegbar. Bitte starte die App neu."}
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=("MVR-Dateien (*.mvr)",)
            )
            if not paths:
                return {"ok": True, "data": {"cancelled": True}}
            return self.load_mvr(paths[0])
        except Exception as e:
            log.exception("Datei-Dialog fehlgeschlagen")
            return {"ok": False, "error": f"Datei-Dialog konnte nicht geoeffnet werden: {e}"}

    def load_mvr(self, path: str) -> dict:
        return self._run_long(lambda: self._do_load_mvr(path))

    def _do_load_mvr(self, path: str) -> dict:
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "Diese Datei wurde nicht gefunden. Pruef bitte den Pfad."}

        scene = read_mvr(path)
        if scene.xml_root is None:
            return {"ok": False, "error": "Diese Datei ist keine gueltige MVR-Datei."}

        types = aggregate_fixture_types(scene)
        stats = compute_stats(scene, types)

        library_dir = self._settings.gdtf_library_dir
        gdtf_library = load_gdtf_library(library_dir) if library_dir else {}

        fixture_names = [t.name for t in types]
        suggestions = find_all_gdtf_suggestions(fixture_names, gdtf_library, {})

        candidates: dict[str, list[Candidate]] = {}
        assignments: dict[str, Assignment] = {}
        for fixture_type in types:
            matches = suggestions.get(fixture_type.name, [])
            candidate_list = [
                Candidate(
                    gdtf_name=gdtf.name,
                    manufacturer=gdtf.manufacturer,
                    revision=gdtf.revision,
                    score=score,
                    modes=[
                        {"name": m.name, "channel_count": m.channel_count} for m in gdtf.modes
                    ],
                    source="library",
                )
                for gdtf, score in matches
            ]
            candidate_list.sort(key=lambda c: c.score, reverse=True)
            candidates[fixture_type.key] = candidate_list

            assignment = Assignment()
            if candidate_list and candidate_list[0].score >= MATCH_THRESHOLD:
                best = candidate_list[0]
                mode_name, confirmed = _resolve_initial_mode(
                    fixture_type.existing_mode, best.modes
                )
                assignment = Assignment(
                    gdtf_name=best.gdtf_name,
                    mode_name=mode_name,
                    removed=False,
                    mode_is_fallback=not confirmed,
                    source="library",
                )
            assignments[fixture_type.key] = assignment

        with self._lock:
            self._scene = scene
            self._types = types
            self._stats = stats
            self._candidates = candidates
            self._assignments = assignments
            self._mvr_path = path
            self._library_dir = library_dir
            self._gdtf_library = gdtf_library
            self._grouping = self._settings.group_by_position
            self._warnings = {"fallbacks": [], "collisions": [], "cleanup_preview": None}
            self._export_state = {"done": False, "path": "", "size_mb": 0.0, "time": ""}

            file_stat = os.stat(path)
            self._file_meta = {
                "name": os.path.basename(path),
                "path": path,
                "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            }

        self._settings.add_recent(path)
        self._settings.save()

        if self._window is not None:
            try:
                self._window.set_title(f"{_BASE_TITLE} — {os.path.basename(path)}")
            except Exception:
                log.exception("Fenstertitel konnte nicht aktualisiert werden")

        return {"ok": True, "data": self.get_state()["data"]}

    def remove_mvr(self) -> dict:
        try:
            with self._lock:
                self._scene = None
                self._types = []
                self._stats = None
                self._candidates = {}
                self._assignments = {}
                self._mvr_path = None
                self._file_meta = {}
                self._warnings = {"fallbacks": [], "collisions": [], "cleanup_preview": None}
                self._export_state = {"done": False, "path": "", "size_mb": 0.0, "time": ""}

            if self._window is not None:
                try:
                    self._window.set_title(_BASE_TITLE)
                except Exception:
                    log.exception("Fenstertitel konnte nicht zurueckgesetzt werden")

            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("remove_mvr fehlgeschlagen")
            return {"ok": False, "error": f"MVR konnte nicht entfernt werden: {e}"}

    def set_active_step(self, n: int) -> dict:
        try:
            self._active_step = int(n)
            return {"ok": True, "data": None}
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"Ungueltiger Schritt: {e}"}

    # ──── Zuordnung ────

    def set_gdtf(self, type_key: str, gdtf_name: str) -> dict:
        try:
            fixture_type = self._type_by_key(type_key)
            if fixture_type is None:
                return {"ok": False, "error": "Diesen Fixture-Typ kenne ich nicht."}

            with self._lock:
                if not gdtf_name:
                    self._assignments[type_key] = Assignment()
                    return {"ok": True, "data": self.get_state()["data"]}

                candidate = self._find_candidate(type_key, gdtf_name)
                if candidate is not None:
                    modes = candidate.modes
                    source = candidate.source
                else:
                    modes = self._modes_from_library(gdtf_name)
                    source = "library"

                mode_name, confirmed = _resolve_initial_mode(
                    fixture_type.existing_mode, modes
                )
                self._assignments[type_key] = Assignment(
                    gdtf_name=gdtf_name,
                    mode_name=mode_name,
                    removed=False,
                    mode_is_fallback=not confirmed,
                    source=source,
                )
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("set_gdtf fehlgeschlagen")
            return {"ok": False, "error": f"GDTF-Zuordnung fehlgeschlagen: {e}"}

    def set_mode(self, type_key: str, mode_name: str) -> dict:
        try:
            with self._lock:
                assignment = self._assignments.get(type_key)
                if assignment is None:
                    return {"ok": False, "error": "Diesen Fixture-Typ kenne ich nicht."}
                assignment.mode_name = mode_name
                assignment.mode_is_fallback = False
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("set_mode fehlgeschlagen")
            return {"ok": False, "error": f"Modus konnte nicht gesetzt werden: {e}"}

    def set_removed(self, type_key: str, flag: bool) -> dict:
        try:
            with self._lock:
                assignment = self._assignments.get(type_key)
                if assignment is None:
                    return {"ok": False, "error": "Diesen Fixture-Typ kenne ich nicht."}
                assignment.removed = bool(flag)
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("set_removed fehlgeschlagen")
            return {"ok": False, "error": f"Entfernen-Status konnte nicht gesetzt werden: {e}"}

    def set_grouping(self, flag: bool) -> dict:
        try:
            with self._lock:
                self._grouping = bool(flag)
            self._settings.group_by_position = self._grouping
            self._settings.save()
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("set_grouping fehlgeschlagen")
            return {"ok": False, "error": f"Gruppierung konnte nicht gesetzt werden: {e}"}

    # ──── GDTF-Bibliothek ────

    def choose_library_dir(self) -> dict:
        try:
            if self._window is None:
                return {"ok": False, "error": "Kein Fenster verfuegbar. Bitte starte die App neu."}
            paths = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            if not paths:
                return {"ok": True, "data": {"cancelled": True}}
            self._settings.gdtf_library_dir = paths[0]
            self._settings.save()
            return self.rescan_library()
        except Exception as e:
            log.exception("Ordner-Dialog fehlgeschlagen")
            return {"ok": False, "error": f"Ordner-Dialog konnte nicht geoeffnet werden: {e}"}

    def rescan_library(self) -> dict:
        return self._run_long(self._do_rescan_library)

    def _do_rescan_library(self) -> dict:
        library_dir = self._settings.gdtf_library_dir
        invalidate_gdtf_cache()
        gdtf_library = load_gdtf_library(library_dir, force_reload=True) if library_dir else {}

        with self._lock:
            self._library_dir = library_dir
            self._gdtf_library = gdtf_library

            for fixture_type in self._types:
                assignment = self._assignments.get(fixture_type.key)
                is_open = assignment is None or (not assignment.removed and not assignment.gdtf_name)
                if is_open:
                    self._candidates[fixture_type.key] = self._build_candidates_for_type(
                        fixture_type
                    )

        return {"ok": True, "data": self.get_state()["data"]}

    # ──── GDTF Share ────

    def share_login(self, user: str, password: str, remember: bool) -> dict:
        return self._run_long(lambda: self._do_share_login(user, password, remember))

    def _do_share_login(self, user: str, password: str, remember: bool) -> dict:
        ok = self._share.login(user, password)
        if not ok:
            return {
                "ok": False,
                "error": self._share.last_error or "Login fehlgeschlagen. Pruef deine Zugangsdaten.",
            }

        self._settings.share_user = user
        if remember:
            try:
                self._settings.share_password_enc = encrypt_password(password)
            except ValueError:
                self._settings.share_password_enc = ""
        else:
            self._settings.share_password_enc = ""
        self._settings.save()

        return {"ok": True, "data": self.get_state()["data"]}

    def share_logout(self) -> dict:
        return self._run_long(self._do_share_logout)

    def _do_share_logout(self) -> dict:
        self._share.logout()
        self._settings.share_user = ""
        self._settings.share_password_enc = ""
        self._settings.save()
        return {"ok": True, "data": self.get_state()["data"]}

    def share_search(self, query: str) -> dict:
        return self._run_long(lambda: self._do_share_search(query))

    def _do_share_search(self, query: str) -> dict:
        results = self._share.search(query)
        if self._share.last_error:
            return {"ok": False, "error": f"Suche fehlgeschlagen: {self._share.last_error}"}
        return {"ok": True, "data": results}

    def share_download(self, rid: int, type_key: str) -> dict:
        return self._run_long(lambda: self._do_share_download(rid, type_key))

    def _do_share_download(self, rid: int, type_key: str) -> dict:
        fixture_type = self._type_by_key(type_key)
        if fixture_type is None:
            return {"ok": False, "error": "Diesen Fixture-Typ kenne ich nicht."}

        library_dir = self._settings.gdtf_library_dir
        if not library_dir:
            return {"ok": False, "error": "Du hast noch keinen GDTF-Bibliotheksordner eingestellt."}

        fixture = self._share.download(rid, library_dir)
        if fixture is None:
            return {"ok": False, "error": self._share.last_error or "Download fehlgeschlagen."}

        invalidate_gdtf_cache()
        gdtf_library = load_gdtf_library(library_dir, force_reload=True)

        with self._lock:
            self._library_dir = library_dir
            self._gdtf_library = gdtf_library
            self._candidates[type_key] = self._build_candidates_for_type(fixture_type)

            modes = [{"name": m.name, "channel_count": m.channel_count} for m in fixture.modes]
            mode_name, confirmed = _resolve_initial_mode(fixture_type.existing_mode, modes)
            self._assignments[type_key] = Assignment(
                gdtf_name=fixture.name,
                mode_name=mode_name,
                removed=False,
                mode_is_fallback=not confirmed,
                source="share",
            )

        return {"ok": True, "data": self.get_state()["data"]}

    # ──── Export ────

    def prepare_export(self) -> dict:
        try:
            if self._scene is None:
                return {"ok": False, "error": "Lade zuerst eine MVR-Datei."}

            with self._lock:
                fallbacks = []
                footprints: dict[str, int] = {}
                for fixture_type in self._types:
                    assignment = self._assignments.get(fixture_type.key)
                    if assignment is None or assignment.removed or not assignment.gdtf_name:
                        continue
                    if assignment.mode_is_fallback:
                        fallbacks.append(
                            ModeFallbackWarning(
                                type_name=fixture_type.name,
                                count=fixture_type.count,
                                gdtf_name=assignment.gdtf_name,
                                mode_name=assignment.mode_name or "",
                            )
                        )
                    channel_count = self._channel_count_for(fixture_type.key, assignment)
                    if channel_count:
                        footprints[fixture_type.key] = channel_count

                collisions = detect_address_collisions(
                    self._scene, self._types, self._assignments, footprints
                )
                cleanup_preview = self._compute_cleanup_preview()

                self._warnings = {
                    "fallbacks": [serialize(f) for f in fallbacks],
                    "collisions": [serialize(c) for c in collisions],
                    "cleanup_preview": cleanup_preview,
                }

            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("prepare_export fehlgeschlagen")
            return {"ok": False, "error": f"Export-Vorbereitung fehlgeschlagen: {e}"}

    def _channel_count_for(self, type_key: str, assignment: Assignment) -> int:
        candidate = self._find_candidate(type_key, assignment.gdtf_name)
        modes = candidate.modes if candidate is not None else self._modes_from_library(
            assignment.gdtf_name
        )
        for mode in modes:
            if mode["name"] == assignment.mode_name:
                return mode["channel_count"]
        return 0

    def _compute_cleanup_preview(self) -> dict:
        """Trockenlauf-Zaehlung ohne ``enrich_mvr`` auszufuehren.

        Zaehlt Fixture-Instanzen offener/entfernter Typen und ermittelt
        eingebettete ``.gdtf``-Dateien, die von keiner verbleibenden
        Zuordnung mehr referenziert werden.
        """
        removed_fixture_count = 0
        open_type_names = []
        kept_gdtf_names: set[str] = set()

        for fixture_type in self._types:
            assignment = self._assignments.get(fixture_type.key)
            if assignment is None or assignment.removed or not assignment.gdtf_name:
                removed_fixture_count += fixture_type.count
                if (
                    assignment is not None
                    and not assignment.removed
                    and not assignment.gdtf_name
                ):
                    open_type_names.append(fixture_type.name)
                continue

            gdtf_name = assignment.gdtf_name
            matched = self._gdtf_library.get(gdtf_name)
            if matched is None:
                matched = find_matching_gdtf(gdtf_name, self._gdtf_library, {})
            if matched is not None:
                abs_path = find_gdtf_file(
                    gdtf_name, self._library_dir, self._gdtf_library, {}, matched=matched
                )
                if abs_path:
                    kept_gdtf_names.add(_clean_gdtf_name(os.path.basename(abs_path)))

        orphan_preview = []
        if self._scene is not None:
            for name in self._scene.embedded_files:
                if name.lower().endswith(".gdtf"):
                    clean_name = _clean_gdtf_name(name)
                    if clean_name not in kept_gdtf_names:
                        orphan_preview.append(clean_name)

        return {
            "removed_fixture_count": removed_fixture_count,
            "orphan_gdtf_names": orphan_preview,
            "open_type_names": open_type_names,
        }

    def run_export(self, path: str = "") -> dict:
        return self._run_long(lambda: self._do_run_export(path))

    def _do_run_export(self, path: str) -> dict:
        if self._scene is None:
            return {"ok": False, "error": "Lade zuerst eine MVR-Datei, bevor du exportierst."}

        if not path:
            if self._window is None:
                return {
                    "ok": False,
                    "error": "Kein Fenster fuer den Speicherdialog verfuegbar.",
                }
            default_path = self._default_export_path()
            directory = os.path.dirname(default_path) or ""
            filename = os.path.basename(default_path) or "export_MA3.mvr"
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=directory,
                save_filename=filename,
                file_types=("MVR-Dateien (*.mvr)",),
            )
            if not result:
                return {"ok": True, "data": {"cancelled": True}}
            path = result if isinstance(result, str) else result[0]

        try:
            # Offene (nicht zugeordnete) Typen zaehlen in enrich_mvr als
            # "removed" (Assignment.gdtf_name ist None) — das ist gewollt:
            # nicht zugeordnete Typen werden beim Export entfernt.
            enrich_result = enrich_mvr(
                self._scene,
                self._types,
                self._assignments,
                self._library_dir,
                self._gdtf_library,
                group_by_position=self._grouping,
            )
        except Exception as e:
            log.exception("Export fehlgeschlagen")
            return {"ok": False, "error": f"Export fehlgeschlagen: {e}"}

        try:
            out_dir = os.path.dirname(path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(path, "wb") as f:
                f.write(enrich_result.data)
        except OSError as e:
            return {"ok": False, "error": f"Die Datei konnte nicht gespeichert werden: {e}"}

        size_mb = round(len(enrich_result.data) / (1024 * 1024), 2)
        time_str = datetime.now().strftime("%H:%M")

        with self._lock:
            self._export_state = {
                "done": True,
                "path": path,
                "size_mb": size_mb,
                "time": time_str,
            }

        self._settings.last_export_dir = os.path.dirname(path) or self._settings.last_export_dir
        self._settings.save()

        return {
            "ok": True,
            "data": {
                "path": path,
                "size_mb": size_mb,
                "time_str": time_str,
                "report": serialize(enrich_result.report),
            },
        }

    def reset_export(self) -> dict:
        try:
            with self._lock:
                self._export_state = {"done": False, "path": "", "size_mb": 0.0, "time": ""}
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("reset_export fehlgeschlagen")
            return {"ok": False, "error": f"Export-Status konnte nicht zurueckgesetzt werden: {e}"}

    def open_folder(self, path: str) -> dict:
        try:
            folder = path if os.path.isdir(path) else os.path.dirname(path)
            if not folder or not os.path.isdir(folder):
                return {"ok": False, "error": "Dieser Ordner wurde nicht gefunden."}
            os.startfile(folder)  # noqa: S606 — Windows-only Anwendung
            return {"ok": True, "data": None}
        except Exception as e:
            log.exception("open_folder fehlgeschlagen")
            return {"ok": False, "error": f"Der Ordner konnte nicht geoeffnet werden: {e}"}

    def get_version(self) -> dict:
        from mvr_enhancer import __version__

        return {"ok": True, "data": __version__}
