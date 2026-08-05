"""GDTF-Parser: Parsing, Scoring und lokale Bibliotheksverwaltung.

Nutzt pygdtf zum Parsen von .gdtf-Dateien und pflegt eine JSON-Cache-
basierte lokale Bibliothek fuer schnelles Nachschlagen und Score-basiertes
Fixture-Matching.

Hinweis: Der GDTF-Share API-Client (Online-Download) lebt in einem
separaten Modul (``share.py``) und wird hier bewusst nicht mitgefuehrt.
"""

import json
import logging
import os
import re
import shutil
import threading
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field

import pygdtf

from mvr_enhancer.core.constants import MAX_GDTF_FILE_SIZE as _MAX_GDTF_FILE_SIZE

log = logging.getLogger(__name__)


# ──── Hilfsfunktionen ────


def _normalize(text: str) -> str:
    """Normalisiert einen Fixture-Namen fuer den Vergleich.

    Ersetzt gaengige Trennzeichen durch Leerzeichen, entfernt
    Mehrfach-Leerzeichen und konvertiert zu Kleinbuchstaben.
    """
    result = text.lower()
    # Trennzeichen vereinheitlichen
    result = re.sub(r"[_\-\.@/\\]+", " ", result)
    # Mehrfach-Leerzeichen und fuehrende/abschliessende Leerzeichen entfernen
    return re.sub(r"\s+", " ", result).strip()


def _tokenize(text: str) -> list[str]:
    """Zerlegt normalisierten Text in Tokens."""
    return _normalize(text).split()


def token_match(query: str, target: str) -> bool:
    """Token-basierter Abgleich: Alle Woerter der Query muessen im Zieltext vorkommen.

    Beispiel: token_match("GLP X5", "GLP Impression X5") → True
    """
    if not query:
        return True
    tokens = _tokenize(query)
    target_norm = _normalize(target)
    return all(t in target_norm for t in tokens)


def score_match(fixture_name: str, gdtf_name: str, manufacturer: str = "") -> float:
    """Berechnet einen Matching-Score zwischen Fixture-Name und GDTF-Eintrag.

    Gibt einen Wert zwischen 0.0 (kein Match) und 1.0 (perfekt) zurueck.

    Scoring-Logik:
    - 1.0: Exakte Uebereinstimmung (nach Normalisierung)
    - 0.9: Fixture-Name ist exakt der GDTF-Name (ohne Hersteller)
    - 0.7-0.85: Alle Tokens des Fixture-Namens im GDTF (oder umgekehrt)
    - 0.5-0.65: Hoher Anteil gemeinsamer Tokens
    - 0.0: Keine relevante Uebereinstimmung
    """
    fix_norm = _normalize(fixture_name)
    gdtf_norm = _normalize(gdtf_name)
    combined_norm = _normalize(f"{manufacturer} {gdtf_name}")

    if not fix_norm or not gdtf_norm:
        return 0.0

    # Exakter Match (normalisiert)
    if fix_norm == gdtf_norm or fix_norm == combined_norm:
        return 1.0

    fix_tokens = set(fix_norm.split())
    gdtf_tokens = set(gdtf_norm.split())
    combined_tokens = set(combined_norm.split())

    if not fix_tokens or not gdtf_tokens:
        return 0.0

    # Fixture-Name ist Teilmenge von GDTF (alle Fixture-Tokens im GDTF)
    fix_in_combined = fix_tokens.issubset(combined_tokens)
    fix_in_gdtf = fix_tokens.issubset(gdtf_tokens)

    # GDTF-Name ist Teilmenge von Fixture
    gdtf_in_fix = gdtf_tokens.issubset(fix_tokens)

    if fix_in_gdtf and gdtf_in_fix:
        # Gleiche Token-Menge, aber nicht exakt gleich (Reihenfolge)
        return 0.95

    if fix_in_gdtf:
        # Alle Fixture-Tokens sind im GDTF-Namen
        ratio = len(fix_tokens) / len(gdtf_tokens) if gdtf_tokens else 0
        base = 0.7 + 0.15 * ratio
        # Bonus wenn Hersteller angegeben und Fixture-Tokens auch in combined
        if manufacturer and fix_in_combined:
            base = min(base + 0.05, 0.95)
        return base

    if gdtf_in_fix:
        # Alle GDTF-Tokens sind im Fixture-Namen
        ratio = len(gdtf_tokens) / len(fix_tokens) if fix_tokens else 0
        return 0.7 + 0.10 * ratio

    if fix_in_combined:
        # Alle Fixture-Tokens in "Manufacturer + Name"
        ratio = len(fix_tokens) / len(combined_tokens) if combined_tokens else 0
        return 0.65 + 0.15 * ratio

    # Anteil gemeinsamer Tokens (Jaccard-aehnlich)
    common = fix_tokens & combined_tokens
    if not common:
        return 0.0

    # Gewichteter Jaccard: wie viel vom Fixture-Namen wurde abgedeckt?
    coverage = len(common) / len(fix_tokens)
    if coverage >= 0.5:
        return 0.4 + 0.25 * coverage

    return 0.0


# ──── Datenmodell ────


@dataclass
class GdtfMode:
    name: str = ""
    channel_count: int = 0


@dataclass
class GdtfFixture:
    manufacturer: str = ""
    name: str = ""
    revision: str = ""
    modes: list[GdtfMode] = field(default_factory=list)


# ──── Lokales Parsing ────


def _extract_revision(file_path: str) -> str:
    """Extrahiert den Revisionsnamen aus dem GDTF-Dateinamen.

    GDTF-Konvention: Manufacturer@Fixture@Revision.gdtf
    """
    import urllib.parse
    basename = os.path.splitext(os.path.basename(file_path))[0]
    decoded = urllib.parse.unquote(basename)
    parts = decoded.split("@")
    if len(parts) >= 3:
        return parts[-1].replace("_", " ")
    return ""


def parse_gdtf(file_path: str) -> GdtfFixture | None:
    """Parst eine .gdtf-Datei mit pygdtf und extrahiert Hersteller, Name und DMX-Modi."""
    try:
        file_size = os.path.getsize(file_path)
        if file_size > _MAX_GDTF_FILE_SIZE:
            log.warning(
                "GDTF-Datei zu gross: %s (%d bytes)", file_path, file_size,
            )
            return None
    except OSError as e:
        log.error("GDTF-Dateigroesse konnte nicht ermittelt werden: %s — %s",
                  file_path, e)
        return None
    try:
        ft = pygdtf.FixtureType(file_path)
    except (zipfile.BadZipFile, OSError) as e:
        log.error("GDTF-Datei konnte nicht geparst werden: %s — %s", file_path, e)
        return None
    try:
        modes = []
        for dmx_mode in ft.dmx_modes:
            modes.append(GdtfMode(
                name=dmx_mode.name,
                channel_count=dmx_mode.dmx_channels_count,
            ))

        return GdtfFixture(
            manufacturer=ft.manufacturer,
            name=ft.name,
            revision=_extract_revision(file_path),
            modes=modes,
        )
    finally:
        try:
            pkg = getattr(ft, '_package', None)
            if pkg is not None:
                pkg.close()
        except (AttributeError, OSError) as e:
            log.debug("GDTF Package-Cleanup fehlgeschlagen: %s", e)


def _cache_path(library_dir: str, fixture_name: str) -> str:
    """Gibt den Pfad zur JSON-Cache-Datei zurueck.

    Bereinigt den Fixture-Namen gruendlich fuer Windows-Dateisysteme:
    Entfernt unerlaubte Zeichen, reservierte Namen und fuehrende/
    abschliessende Punkte/Leerzeichen.
    """
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', fixture_name)
    safe = safe.strip('. ')
    if not safe:
        safe = '_unnamed'
    # Windows-reservierte Namen blockieren
    if re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)$', safe, re.IGNORECASE):
        safe = f"_{safe}"
    return os.path.join(library_dir, f"{safe}.json")


def _save_cache(library_dir: str, fixture: GdtfFixture) -> None:
    """Speichert geparste Fixture-Daten als JSON-Cache (atomar)."""
    path = _cache_path(library_dir, fixture.name)
    data = {
        "manufacturer": fixture.manufacturer,
        "name": fixture.name,
        "revision": fixture.revision,
        "modes": [{"name": m.name, "channel_count": m.channel_count} for m in fixture.modes],
    }
    import tempfile
    fd, tmp_path = tempfile.mkstemp(dir=library_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_cache(path: str) -> GdtfFixture | None:
    """Laedt eine gecachte Fixture-Definition."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return GdtfFixture(
            manufacturer=data.get("manufacturer", ""),
            name=data.get("name", ""),
            revision=data.get("revision", ""),
            modes=[GdtfMode(**m) for m in data.get("modes", [])],
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("GDTF-Cache konnte nicht geladen werden: %s", e)
        return None


def import_gdtf(file_path: str, library_dir: str) -> GdtfFixture | None:
    """Importiert eine .gdtf-Datei in die Bibliothek (kopieren + parsen + cachen)."""
    os.makedirs(library_dir, exist_ok=True)
    fixture = parse_gdtf(file_path)
    if fixture is None:
        log.warning("GDTF-Datei konnte nicht geparst werden: %s", file_path)
        return None

    # .gdtf-Datei in Library kopieren
    dest = os.path.join(library_dir, os.path.basename(file_path))
    if os.path.abspath(file_path) != os.path.abspath(dest):
        shutil.copy2(file_path, dest)

    _save_cache(library_dir, fixture)
    invalidate_gdtf_cache()
    log.info("GDTF importiert: %s (%d Modi)", fixture.name, len(fixture.modes))
    return fixture


_lib_cache: dict[str, GdtfFixture] | None = None
_lib_cache_dir: str = ""
_lib_cache_mtime: float = 0.0
_lib_lock = threading.Lock()


def load_gdtf_library(library_dir: str, force_reload: bool = False) -> dict[str, GdtfFixture]:
    """Laedt alle gecachten GDTF-Fixtures aus dem Bibliotheks-Ordner.

    Verwendet einen In-Memory Cache — erneutes Laden nur wenn sich das
    Verzeichnis geaendert hat oder force_reload=True.

    Nach dem JSON-Cache-Durchlauf werden zusaetzlich rohe ``.gdtf``-Dateien
    ohne zugehoerigen JSON-Cache eingelesen (z.B. manuell in den Ordner
    kopierte Dateien): Sie werden mit ``parse_gdtf`` geparst, dem Ergebnis-
    Dict hinzugefuegt (sofern der Fixture-Name noch nicht vorhanden ist)
    und via ``_save_cache`` als JSON gecacht, damit Folge-Scans schnell
    bleiben. Defekte Dateien werden geloggt und uebersprungen.
    """
    global _lib_cache, _lib_cache_dir, _lib_cache_mtime

    if not library_dir or not os.path.isdir(library_dir):
        return {}

    try:
        # NOTE: os.path.getmtime on a directory only updates when files are
        # added/removed, NOT when existing files are modified.  A full
        # invalidation (force_reload=True or invalidate_gdtf_cache()) is
        # needed after in-place edits to cached JSON files.
        mtime = os.path.getmtime(library_dir)
    except OSError:
        mtime = 0.0

    with _lib_lock:
        if (not force_reload
                and _lib_cache is not None
                and _lib_cache_dir == library_dir
                and mtime == _lib_cache_mtime):
            return _lib_cache

        library: dict[str, GdtfFixture] = {}
        for filename in os.listdir(library_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(library_dir, filename)
            fixture = _load_cache(path)
            if fixture:
                library[fixture.name] = fixture

        # Rohe .gdtf-Dateien ohne JSON-Cache mitscannen (z.B. manuell
        # in den Ordner kopierte Dateien) und fuer Folge-Scans cachen.
        for filename in os.listdir(library_dir):
            if not filename.lower().endswith(".gdtf"):
                continue
            path = os.path.join(library_dir, filename)
            fixture = parse_gdtf(path)
            if fixture is None:
                log.warning(
                    "GDTF-Datei konnte nicht geparst werden (uebersprungen): %s", path,
                )
                continue
            if fixture.name in library:
                continue
            library[fixture.name] = fixture
            _save_cache(library_dir, fixture)

        _lib_cache = library
        _lib_cache_dir = library_dir
        _lib_cache_mtime = mtime
        return library


def invalidate_gdtf_cache():
    """Setzt den GDTF-Bibliothek-Cache zurueck (z.B. nach Import)."""
    global _lib_cache, _gdtf_file_index, _gdtf_file_index_dir, _gdtf_file_index_mtime
    with _lib_lock:
        _lib_cache = None
        _gdtf_file_index = None
        _gdtf_file_index_dir = ""
        _gdtf_file_index_mtime = 0.0
    with _score_cache_lock:
        _score_cache.clear()


_score_cache: OrderedDict[tuple[str, str, str], float] = OrderedDict()
_score_cache_lock = threading.Lock()
_SCORE_CACHE_MAX = 5000


def _cached_score_match(fixture_name: str, gdtf_name: str, manufacturer: str = "") -> float:
    """score_match() mit In-Memory-Cache (FIFO-Eviction, thread-safe).

    Verwendet einen eigenen Lock (_score_cache_lock), um Kontention
    mit dem Bibliotheks-Lock (_lib_lock) zu vermeiden.
    """
    key = (fixture_name, gdtf_name, manufacturer)
    with _score_cache_lock:
        cached = _score_cache.get(key)
        if cached is not None:
            return cached
    score = score_match(fixture_name, gdtf_name, manufacturer)
    with _score_cache_lock:
        if len(_score_cache) >= _SCORE_CACHE_MAX:
            # Aelteste Haelfte entfernen (FIFO) statt komplett zu loeschen
            for _ in range(_SCORE_CACHE_MAX // 2):
                _score_cache.popitem(last=False)
        _score_cache[key] = score
    return score


# ──── Shared GDTF-Matching ────


def find_matching_gdtf(
    fixture_name: str,
    gdtf_library: dict[str, GdtfFixture],
    gdtf_overrides: dict[str, str],
) -> GdtfFixture | None:
    """Findet die passende GDTF-Definition fuer einen Fixture-Namen.

    Prueft zuerst manuelle Overrides, dann Score-basiertes Matching
    mit einem Mindest-Score von 0.6.
    """
    # Manuelles Override pruefen
    if fixture_name in gdtf_overrides:
        override = gdtf_overrides[fixture_name]
        if override == "":
            return None
        if override in gdtf_library:
            return gdtf_library[override]

    # Score-basiertes Matching
    best_match, best_score = find_best_gdtf_match(fixture_name, gdtf_library)
    if best_match and best_score >= MATCH_THRESHOLD:
        return best_match

    return None


# Mindest-Score fuer automatisches Matching
MATCH_THRESHOLD = 0.6


def find_best_gdtf_match(
    fixture_name: str,
    gdtf_library: dict[str, GdtfFixture],
) -> tuple[GdtfFixture | None, float]:
    """Findet den besten GDTF-Match mit Score.

    Gibt (GdtfFixture, score) zurueck. Score 0.0 bedeutet kein Match.
    Nuetzlich fuer UI-Vorschlaege auch unterhalb des Auto-Match-Schwellenwerts.
    """
    best: GdtfFixture | None = None
    best_score = 0.0

    for gdtf_name, gdtf_fixture in gdtf_library.items():
        score = _cached_score_match(fixture_name, gdtf_name, gdtf_fixture.manufacturer)
        if score > best_score:
            best_score = score
            best = gdtf_fixture

    return best, best_score


def find_all_gdtf_suggestions(
    fixture_names: list[str],
    gdtf_library: dict[str, GdtfFixture],
    gdtf_overrides: dict[str, str],
    *,
    top_n: int = 5,
    threshold: float = 0.3,
) -> dict[str, list[tuple[GdtfFixture, float]]]:
    """Findet GDTF-Vorschlaege fuer mehrere Fixture-Namen auf einmal.

    Gibt ein Dict zurueck: fixture_name → [(GdtfFixture, score), ...] sortiert nach Score.
    Nur Eintraege mit Score > ``threshold`` werden eingeschlossen, begrenzt auf
    die besten ``top_n`` Kandidaten pro Fixture-Namen.
    Fixture-Namen mit bestehendem Override werden uebersprungen.
    """
    suggestions: dict[str, list[tuple[GdtfFixture, float]]] = {}

    for fixture_name in fixture_names:
        # Override vorhanden → ueberspringen
        if fixture_name in gdtf_overrides:
            continue

        matches: list[tuple[GdtfFixture, float]] = []
        for gdtf_name, gdtf_fixture in gdtf_library.items():
            score = _cached_score_match(fixture_name, gdtf_name, gdtf_fixture.manufacturer)
            if score > threshold:
                matches.append((gdtf_fixture, score))

        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            suggestions[fixture_name] = matches[:top_n]

    return suggestions


_gdtf_file_index: dict[str, str] | None = None
_gdtf_file_index_dir: str = ""
_gdtf_file_index_mtime: float = 0.0


def _build_gdtf_file_index(gdtf_library_dir: str) -> dict[str, str]:
    """Erstellt einen Index aller .gdtf-Dateien: normalisierter_name -> dateiname."""
    import urllib.parse
    index: dict[str, str] = {}
    for fname in os.listdir(gdtf_library_dir):
        if not fname.lower().endswith(".gdtf"):
            continue
        decoded = fname.lower().replace(" ", "_").replace("@", "_")
        unquoted = urllib.parse.unquote(decoded)
        index[unquoted] = fname
    return index


def _get_gdtf_file_index(gdtf_library_dir: str) -> dict[str, str]:
    """Gibt den gecachten GDTF-Datei-Index zurueck (mit mtime-Pruefung, thread-safe)."""
    global _gdtf_file_index, _gdtf_file_index_dir, _gdtf_file_index_mtime
    try:
        mtime = os.path.getmtime(gdtf_library_dir)
    except OSError:
        return {}
    with _lib_lock:
        if (_gdtf_file_index is not None
                and _gdtf_file_index_dir == gdtf_library_dir
                and mtime == _gdtf_file_index_mtime):
            return _gdtf_file_index
    index = _build_gdtf_file_index(gdtf_library_dir)
    with _lib_lock:
        _gdtf_file_index = index
        _gdtf_file_index_dir = gdtf_library_dir
        _gdtf_file_index_mtime = mtime
    return index


def find_gdtf_file(
    fixture_name: str,
    gdtf_library_dir: str,
    gdtf_library: dict[str, GdtfFixture],
    gdtf_overrides: dict[str, str],
    matched: "GdtfFixture | None" = None,
) -> str | None:
    """Findet die .gdtf-Datei im Bibliotheksordner fuer einen Fixture-Namen.

    Gibt den vollstaendigen Dateipfad zurueck oder None.
    Falls matched bereits bekannt ist, kann es uebergeben werden um
    einen doppelten find_matching_gdtf-Aufruf zu vermeiden.
    """
    if matched is None:
        matched = find_matching_gdtf(fixture_name, gdtf_library, gdtf_overrides)
    if not matched or not gdtf_library_dir:
        return None
    target = matched.name.lower().replace(" ", "_").replace("@", "_")
    file_index = _get_gdtf_file_index(gdtf_library_dir)
    for decoded_name, fname in file_index.items():
        if target in decoded_name:
            return os.path.join(gdtf_library_dir, fname)
    return None
