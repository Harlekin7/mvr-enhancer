"""Read-only Abgleich mit einer lokalen VectorWatch-Installation.

VectorWatch (separates Tool, gleicher Rechner) persistiert seine Projekte
als JSON unter ``%APPDATA%/VectorWatch/projects`` und seine GDTF-Bibliothek
unter ``%APPDATA%/VectorWatch/gdtf_library`` (beide Pfade optional in der
globalen ``config.json`` verlegt). Dieses Modul liest beides ausschliesslich
lesend: es sucht das zum Namen der geladenen MVR-Datei passende Projekt,
prueft ueber den im Projekt gespeicherten Fixture-Snapshot, ob das Projekt
inhaltlich zur MVR passt (``COVERAGE_THRESHOLD``), und loest die dort
kuratierten Zuordnungen (``dmx_gdtf_overrides``/``dmx_mode_overrides``)
plus Score-Auto-Matches gegen die VectorWatch-Bibliothek auf.

Fail-silent per Vertrag: jeder Defekt (fehlende Installation, kaputtes
JSON, fehlende Dateien) fuehrt zu einem Ergebnis-Status, nie zu einer
Exception nach aussen — der Ladepfad des Enhancers darf am Abgleich
niemals scheitern. In VectorWatch-Verzeichnisse wird niemals geschrieben.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field

from mvr_enhancer.core.gdtf import (
    MATCH_THRESHOLD,
    GdtfFixture,
    GdtfMode,
    _normalize,
    find_best_gdtf_match,
    find_gdtf_file,
)

log = logging.getLogger(__name__)

# Mindestanteil der MVR-Fixture-Typen, die im Fixture-Snapshot des
# VectorWatch-Projekts vorkommen muessen, damit ein Namens-Treffer als
# inhaltlich passendes Projekt gilt (bewusst Konstante, kein Setting).
COVERAGE_THRESHOLD = 0.7


@dataclass
class VwAssignment:
    """Eine aus VectorWatch uebernommene GDTF-Zuordnung fuer einen Fixture-Typ."""

    type_name: str  # angefragter Typ-Name (Anzeigename aus dem MVR)
    gdtf_name: str  # GdtfFixture.name in der VectorWatch-Bibliothek ("" bei "none")
    gdtf_file: str  # absoluter Pfad zur .gdtf in der VectorWatch-Bibliothek
    mode: str  # DMX-Modus-Override aus dem VectorWatch-Projekt ("" wenn keiner)
    source: str  # "override" | "auto" | "none"


@dataclass
class VwSyncResult:
    """Ergebnis eines Abgleichs; ``status`` beschreibt den Ausgang.

    Status-Werte: ``"matched"`` (Projekt gefunden, Zuordnungen geliefert),
    ``"no_project"`` (kein Projekt mit passendem Namen), ``"low_coverage"``
    (Projekt gefunden, deckt aber weniger als ``COVERAGE_THRESHOLD`` der
    angefragten Typen ab), ``"unavailable"`` (keine lesbare
    VectorWatch-Installation).
    """

    status: str
    project_name: str = ""
    coverage: float = 0.0
    assignments: list[VwAssignment] = field(default_factory=list)


def _normalize_project_match(name: str) -> str:
    """Normalisiert Datei-/Projektnamen fuer das Projekt-Fuzzy-Matching.

    Portiert aus vw-tool-gpa ``app/vectorwatch/parsing/mvr.py``
    (``_normalize_for_match``), damit beide Tools dieselbe Logik verwenden.
    """
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r"[\s_\-]+", " ", name)
    return name.strip()


def _project_matches(norm_project: str, norm_mvr: str) -> bool:
    """Wort-basiertes Matching Projektname <-> MVR-Dateiname (beide normalisiert)."""
    if not norm_project or not norm_mvr:
        return False
    project_words = set(norm_project.split())
    mvr_words = set(norm_mvr.split())
    return (
        norm_project == norm_mvr
        or norm_project in norm_mvr
        or norm_mvr in norm_project
        or project_words <= mvr_words
        or mvr_words <= project_words
    )


def _string_dict(value) -> dict[str, str]:
    """Filtert ein Mapping defensiv auf str->str-Paare (kaputte Typen fliegen raus)."""
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


class VectorWatchProvider:
    """Liest Projekte und GDTF-Bibliothek einer lokalen VectorWatch-Installation.

    Alle Zugriffe sind strikt lesend; es werden weder Caches noch sonstige
    Dateien in VectorWatch-Verzeichnisse geschrieben.
    """

    def __init__(self, appdata_dir: str | None = None):
        if appdata_dir is None:
            base = os.environ.get("APPDATA", "")
            appdata_dir = os.path.join(base, "VectorWatch") if base else ""
        self._appdata_dir = appdata_dir

    def is_available(self) -> bool:
        """True, wenn eine VectorWatch-Installation (AppData-Ordner) existiert."""
        return bool(self._appdata_dir) and os.path.isdir(self._appdata_dir)

    def get_assignments(self, mvr_name: str, type_names: list[str]) -> VwSyncResult:
        """Sucht das zur MVR passende Projekt und loest dessen Zuordnungen auf.

        Args:
            mvr_name: Dateiname der geladenen MVR (z.B. ``"Sommerfest 2026.mvr"``).
            type_names: Anzeigenamen der Fixture-Typen aus der MVR.

        Returns:
            VwSyncResult mit Status und (bei ``"matched"``) den aufgeloesten
            Zuordnungen. Typen ohne Treffer in VectorWatch fehlen in
            ``assignments`` — fuer sie greift das lokale Matching des Aufrufers.
        """
        if not self.is_available():
            return VwSyncResult(status="unavailable")
        requested = [(name, _normalize(name)) for name in type_names if name]
        if not requested:
            return VwSyncResult(status="no_project")

        config = self._read_json(os.path.join(self._appdata_dir, "config.json"))
        config = config if isinstance(config, dict) else {}
        projects_dir = self._resolve_dir(config.get("projects_dir"), "projects")

        found = self._find_matching_project(mvr_name, projects_dir)
        if found is None:
            return VwSyncResult(status="no_project")
        project_name, project = found

        coverage = self._compute_coverage(project, requested)
        if coverage < COVERAGE_THRESHOLD:
            return VwSyncResult(
                status="low_coverage", project_name=project_name, coverage=coverage
            )

        library_dir = self._resolve_dir(config.get("gdtf_library_dir"), "gdtf_library")
        vw_library = self._load_vw_library(library_dir)

        overrides_by_norm = {
            _normalize(k): v
            for k, v in _string_dict(project.get("dmx_gdtf_overrides")).items()
            if _normalize(k)
        }
        modes_by_norm = {
            _normalize(k): v
            for k, v in _string_dict(project.get("dmx_mode_overrides")).items()
            if _normalize(k)
        }

        assignments = []
        for name, norm in requested:
            assignment = self._resolve_type(
                name, norm, overrides_by_norm, modes_by_norm, vw_library, library_dir
            )
            if assignment is not None:
                assignments.append(assignment)

        return VwSyncResult(
            status="matched",
            project_name=project_name,
            coverage=coverage,
            assignments=assignments,
        )

    # ──── Interna ────

    def _resolve_dir(self, configured, default_name: str) -> str:
        """Konfigurierten Pfad nutzen, sonst den Standardordner unter AppData."""
        if isinstance(configured, str) and configured and os.path.isdir(configured):
            return configured
        return os.path.join(self._appdata_dir, default_name)

    def _find_matching_project(
        self, mvr_name: str, projects_dir: str
    ) -> tuple[str, dict] | None:
        """Sucht das zum MVR-Dateinamen passende Projekt-JSON.

        Matching wie in VectorWatch (``find_source_mvr``), nur in
        Gegenrichtung: exakt / enthaelt / Wort-Teilmenge. Bei mehreren
        Treffern gewinnt die zuletzt geaenderte Projektdatei; nicht lesbare
        Treffer werden uebersprungen (naechster Kandidat).
        """
        if not os.path.isdir(projects_dir):
            return None
        norm_mvr = _normalize_project_match(mvr_name)
        if not norm_mvr:
            return None

        candidates: list[tuple[float, str, str]] = []
        try:
            entries = list(os.scandir(projects_dir))
        except OSError as e:
            log.warning("VectorWatch-Projektordner nicht lesbar: %s", e)
            return None
        for entry in entries:
            if not entry.is_file() or not entry.name.lower().endswith(".json"):
                continue
            project_name = os.path.splitext(entry.name)[0]
            if not _project_matches(_normalize_project_match(project_name), norm_mvr):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, project_name, entry.path))

        candidates.sort(key=lambda c: c[0], reverse=True)
        for _mtime, project_name, path in candidates:
            data = self._read_json(path)
            if isinstance(data, dict):
                return project_name, data
        return None

    @staticmethod
    def _compute_coverage(project: dict, requested: list[tuple[str, str]]) -> float:
        """Anteil der angefragten Typen, die der Fixture-Snapshot des Projekts kennt.

        Ohne (verwertbaren) Snapshot ist keine inhaltliche Pruefung moeglich —
        dann gilt konservativ 0.0, und der Aufrufer behandelt das Projekt wie
        einen Namens-Zufallstreffer (``low_coverage``).
        """
        snapshot = project.get("snapshot")
        fixtures = snapshot.get("fixtures") if isinstance(snapshot, dict) else None
        if not isinstance(fixtures, list):
            return 0.0
        snapshot_names = {
            _normalize(f.get("name", "")) for f in fixtures if isinstance(f, dict)
        }
        snapshot_names.discard("")
        if not snapshot_names:
            return 0.0
        covered = sum(1 for _name, norm in requested if norm in snapshot_names)
        return covered / len(requested)

    def _load_vw_library(self, library_dir: str) -> dict[str, GdtfFixture]:
        """Laedt die VectorWatch-GDTF-Bibliothek rein lesend.

        Zuerst ueber die aggregierte ``index.json``; fehlt sie, ueber die pro
        Fixture abgelegten JSON-Cache-Dateien (gleiches Eintrags-Schema).
        Rohe ``.gdtf``-Dateien werden bewusst NICHT geparst: das waere
        langsam, und der Enhancer schreibt niemals Caches in den
        VectorWatch-Ordner.
        """
        if not library_dir or not os.path.isdir(library_dir):
            return {}
        index = self._read_json(os.path.join(library_dir, "index.json"))
        if isinstance(index, dict):
            library = self._library_from_entries(index.get("fixtures"))
            if library:
                return library

        entries = []
        try:
            filenames = os.listdir(library_dir)
        except OSError as e:
            log.warning("VectorWatch-Bibliothek nicht lesbar: %s", e)
            return {}
        for filename in filenames:
            if not filename.endswith(".json") or filename == "index.json":
                continue
            data = self._read_json(os.path.join(library_dir, filename))
            if isinstance(data, dict):
                entries.append(data)
        return self._library_from_entries(entries)

    @staticmethod
    def _library_from_entries(entries) -> dict[str, GdtfFixture]:
        """Baut GdtfFixture-Objekte aus Index-/Cache-Eintraegen (defensiv)."""
        library: dict[str, GdtfFixture] = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            try:
                name = entry["name"]
                if not name:
                    continue
                library[name] = GdtfFixture(
                    manufacturer=entry.get("manufacturer", ""),
                    name=name,
                    revision=entry.get("revision", ""),
                    modes=[GdtfMode(**m) for m in entry.get("modes", [])],
                )
            except (KeyError, TypeError) as e:
                log.warning("VectorWatch-Bibliothekseintrag uebersprungen: %s", e)
                continue
        return library

    @staticmethod
    def _resolve_type(
        name: str,
        norm: str,
        overrides_by_norm: dict[str, str],
        modes_by_norm: dict[str, str],
        vw_library: dict[str, GdtfFixture],
        library_dir: str,
    ) -> VwAssignment | None:
        """Loest einen Fixture-Typ gegen Overrides und VW-Bibliothek auf.

        Rangfolge wie in VectorWatch selbst: manueller Override zuerst
        (leerer String = bewusst kein Match), sonst Score-Matching; ein
        Override, der nicht mehr in der Bibliothek existiert, faellt auf das
        Score-Matching zurueck. Ohne aufloesbare Datei wird ``None``
        geliefert — dann uebernimmt das lokale Matching des Aufrufers.
        """
        fixture: GdtfFixture | None = None
        source = "auto"
        if norm in overrides_by_norm:
            override = overrides_by_norm[norm]
            if override == "":
                return VwAssignment(
                    type_name=name, gdtf_name="", gdtf_file="", mode="", source="none"
                )
            fixture = vw_library.get(override)
            if fixture is not None:
                source = "override"
        if fixture is None:
            best, score = find_best_gdtf_match(name, vw_library)
            if best is None or score < MATCH_THRESHOLD:
                return None
            fixture = best
        file_path = find_gdtf_file(name, library_dir, vw_library, {}, matched=fixture)
        if not file_path:
            return None
        return VwAssignment(
            type_name=name,
            gdtf_name=fixture.name,
            gdtf_file=file_path,
            mode=modes_by_norm.get(norm, ""),
            source=source,
        )

    @staticmethod
    def _read_json(path: str):
        """Liest eine JSON-Datei defensiv; jeder Defekt ergibt ``None``."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            log.warning("VectorWatch-Datei nicht lesbar: %s — %s", path, e)
            return None
