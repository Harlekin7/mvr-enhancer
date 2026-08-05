# MVR Enhancer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows-Desktop-App (eine .exe), die ein Vectorworks-MVR lädt, pro Fixture-Typ eine GDTF + DMX-Modus zuordnet (Score-Vorschläge, lokale Bibliothek + GDTF Share) und ein bereinigtes, grandMA3-sicheres MVR exportiert — UI pixelgenau nach `design_handoff_mvr_export_tool/`.

**Architecture:** Ein Python-Paket. pywebview zeigt `mvr_enhancer/ui/` (Vanilla HTML/CSS/JS) in einem nativen Fenster (Client-Area 1280×1000); `api.py` ist die JS↔Python-Bridge und hält den App-Zustand; `core/` enthält die aus `Vectorworks-Tool-GPA` portierten Parsing-Module plus neue Analyse-/Enricher-Logik. PyInstaller erzeugt die .exe; GitHub Actions baut Releases.

**Tech Stack:** Python 3.12, pywebview≥5, pygdtf, defusedxml, certifi, pytest, ruff, PyInstaller≥6, GitHub Actions (windows-latest).

**Maßgebliche Dokumente (vor jeder Task lesen, soweit genannt):**
- Spec: `docs/superpowers/specs/2026-08-05-mvr-enhancer-design.md`
- Design-Handoff: `design_handoff_mvr_export_tool/README.md` (+ Prototyp-HTML)
- Portierungsquelle (geklont): `C:\Users\s.fabisch\AppData\Local\Temp\claude\c--Dev-MVR-Enhancer\ec1ecf7a-8f29-4bdf-b2b5-3bc469fa4881\scratchpad\vw-tool-gpa` — im Folgenden `<SRC>`. Falls der Ordner fehlt: `git clone --depth 1 --branch m1-5-ui-smoke https://github.com/Harlekin7/Vectorworks-Tool-GPA.git <SRC>`

## Global Constraints

- Python `>=3.10` (Union-Syntax `X | Y` ohne `__future__`), Ziel-Interpreter 3.12.
- Runtime-Dependencies ausschließlich: `pywebview>=5,<7`, `pygdtf>=1.0.0,<2`, `defusedxml>=0.7.1,<1`, `certifi>=2024.1.0`. Dev: `pytest>=7,<11`, `ruff`, `pyinstaller>=6`.
- UI-Sprache Deutsch, informelles „du"; Copy exakt aus dem Handoff übernehmen.
- Farb-/Maßwerte: Token-Dateien gewinnen gegen README-Prosa. Insbesondere `--blue-600` = **#1e7cc4**, `--border-dark` = **rgba(255,255,255,0.12)**, `--radius-md` = **6px**.
- Score-Schwellen: ≥0.90 success · 0.30–0.89 warning · <0.30 danger; Kandidaten-Threshold >0.3, Anzeige `toFixed(2)`.
- Keine Netz-Zugriffe der UI (keine CDNs): Fonts/Icons/Bild lokal gebündelt. Einzige Netz-Nutzung: GDTF-Share-Client (`https://gdtf-share.com/apis/public`).
- Sicherheits-Limits (aus `<SRC>/app/vectorwatch/constants.py`): MAX_MVR_XML_SIZE=500 MB, MAX_MVR_EMBEDDED_FILE_COUNT=1000, MAX_MVR_EMBEDDED_FILE_SIZE=100 MB, MAX_MVR_TOTAL_EXTRACTED=500 MB, MAX_GDTF_FILE_SIZE=200 MB, MAX_GDTF_DOWNLOAD_SIZE=200 MB.
- Reproduzierbare UUIDs: `uuid.uuid5(uuid.NAMESPACE_DNS, seed)`; Seeds `"layer_MVR Enhancer Export"`, `f"group_{position}"`, `"group_3D"`.
- Jede Task: Tests zuerst (TDD), `ruff check .` sauber, eigener Commit auf `main`.
- Versions-String: `v0.1.0 · DIN SPEC 15801 · MVR 1.6`.

---

## Phase A — Gerüst

### Task 1: Projekt-Skeleton + Tooling

**Files:**
- Create: `pyproject.toml`, `mvr_enhancer/__init__.py`, `mvr_enhancer/__main__.py`, `tests/__init__.py`, `tests/test_smoke.py`, `ruff.toml`, `.github/workflows/ci.yml`
- Modify: `.gitignore` (ergänzen: `__pycache__/`, `dist/`, `build/pyinstaller-out/`, `*.spec.bak`, `.venv/`, `*.egg-info/`)

**Interfaces:**
- Produces: `mvr_enhancer.__version__ = "0.1.0"`; pytest-Konfiguration `testpaths=["tests"]`, `pythonpath=["."]`.

- [ ] **Step 1:** `pyproject.toml` schreiben: `[project] name="mvr-enhancer", version="0.1.0", requires-python=">=3.10"`, dependencies laut Global Constraints, `[project.optional-dependencies] dev=["pytest>=7,<11","ruff","pyinstaller>=6"]`, `[tool.pytest.ini_options] testpaths=["tests"]`, `pythonpath=["."]`. `ruff.toml`: `line-length = 100`, `[lint] select = ["E","F","W","I","UP"]`, `ignore = ["E501"]`.
- [ ] **Step 2:** Paket anlegen: `mvr_enhancer/__init__.py` mit `__version__ = "0.1.0"`; `__main__.py` mit `from mvr_enhancer.main import run` in `if __name__ == "__main__": run()` (Import in Funktion kapseln, `main.py` existiert erst in Task 10 — bis dahin `raise SystemExit("UI folgt")` als Body von `run` NICHT nötig: `__main__.py` erst in Task 10 mit Inhalt füllen; hier nur leere Datei mit Kommentar `# Entry point folgt in main.py`).
- [ ] **Step 3:** `tests/test_smoke.py`: `def test_version(): import mvr_enhancer; assert mvr_enhancer.__version__ == "0.1.0"`.
- [ ] **Step 4:** venv anlegen + install: `python -m venv .venv; .venv\Scripts\pip install -e .[dev]`. Run: `.venv\Scripts\python -m pytest -q` → 1 passed. `.venv\Scripts\ruff check .` → sauber.
- [ ] **Step 5:** `.github/workflows/ci.yml`: on push/PR; `windows-latest`; setup-python 3.12; `pip install -e .[dev]`; `ruff check .`; `pytest -q`.
- [ ] **Step 6:** Commit `chore: project skeleton, tooling, CI`.

### Task 2: Test-Fixture-Builder (MVR/GDTF programmatisch)

**Files:**
- Create: `tests/builders.py`, `tests/test_builders.py`

**Interfaces:**
- Produces (von fast allen Folge-Tasks konsumiert):
  - `build_gdtf(path: Path, *, manufacturer="Testlight", name="Beam One", revision="rev1", modes=(("Mode 1", 16), ("Mode 2", 32))) -> Path` — schreibt minimale pygdtf-lesbare `.gdtf` (ZIP mit `description.xml`: `FixtureType` mit `Name`,`Manufacturer`; je Modus `DMXMode` mit `DMXChannels`-Kindern in passender Anzahl, Attribut `Name`).
  - `build_mvr(path: Path, *, fixtures: list[dict], embedded: dict[str, bytes] = {}, aux_positions: dict[str, str] = {}, poison=False) -> Path` — ZIP mit `GeneralSceneDescription.xml`. `fixtures`-Dicts: `{name, uuid, gdtf_spec, gdtf_mode, address (absolut), position_uuid, layer}`. `poison=True` fügt jedem Fixture `<CustomCommands><CustomCommand>f 0.000000</CustomCommand></CustomCommands>` und `<Position>{uuid ohne Definition}</Position>` hinzu. `aux_positions` erzeugt `AUXData/Positions/Position`-Definitionen (UUID→Name). `embedded` legt zusätzliche ZIP-Einträge an (z. B. verwaiste `Orphan@Old@r0.gdtf`, `mesh1.glb`).
  - XML-Grundgerüst: `<GeneralSceneDescription verMajor="1" verMinor="5"><Scene><Layers><Layer name=...><ChildList><Fixture name=... uuid=...><GDTFSpec>…</GDTFSpec><GDTFMode>…</GDTFMode><Addresses><Address break="0">…</Address></Addresses><Matrix>…</Matrix></Fixture>…`
- [ ] **Step 1:** `tests/test_builders.py` schreiben: `test_gdtf_readable_by_pygdtf` (pygdtf.FixtureType(str(p)) liefert name/manufacturer/2 Modi), `test_mvr_is_zip_with_xml` (zipfile öffnet, XML parsebar, Fixture-Count stimmt, poison-Variante enthält `CustomCommands`).
- [ ] **Step 2:** Run → FAIL (builders fehlt).
- [ ] **Step 3:** `tests/builders.py` implementieren.
- [ ] **Step 4:** Run → PASS. Commit `test: programmatic MVR/GDTF fixture builders`.

## Phase B — Core-Port

### Task 3: constants + _coerce + mvr_reader portieren

**Files:**
- Create: `mvr_enhancer/core/__init__.py` (leer), `mvr_enhancer/core/constants.py`, `mvr_enhancer/core/_coerce.py`, `mvr_enhancer/core/mvr_reader.py`
- Create: `tests/test_coerce.py`, `tests/test_mvr_reader.py`

**Interfaces:**
- Produces: `read_mvr(path: str) -> MvrScene`; `MvrScene(xml_root, fixtures: list[MvrFixture], non_fixture_elements, embedded_files: dict[str, bytes], user_data, aux_data)`; `MvrFixture(element, uuid, name, gdtf_spec, gdtf_mode, dmx_address, matrix)` — Felder exakt wie `<SRC>/app/vectorwatch/parsing/mvr_reader.py:42-64`.

- [ ] **Step 1:** Kopieren: `<SRC>/app/vectorwatch/parsing/_coerce.py` → `core/_coerce.py` (unverändert); `<SRC>/app/vectorwatch/constants.py` Zeilen mit MVR-/GDTF-Limits (Z. 31-39) → `core/constants.py`; `<SRC>/app/vectorwatch/parsing/mvr_reader.py` → `core/mvr_reader.py`, Import `from vectorwatch.constants import …` → `from mvr_enhancer.core.constants import …`.
- [ ] **Step 2:** Tests kopieren/anpassen: `<SRC>/app/tests/test_coerce.py` → `tests/test_coerce.py` (Imports auf `mvr_enhancer.core._coerce`). Neu `tests/test_mvr_reader.py` mit builders: `test_reads_fixtures_and_embedded`, `test_rejects_oversized_xml` (Limit per monkeypatch auf 10 Bytes → ValueError), `test_zip_bomb_file_count` (monkeypatch Count-Limit=1, MVR mit 2 embedded → ValueError), `test_bad_zip_returns_empty_scene` (Textdatei als .mvr → leere MvrScene), `test_path_traversal_entries_skipped` (embedded-Eintrag `..\\evil.txt` → nicht in `embedded_files`).
- [ ] **Step 3:** Run → Traversal-Test FAIL (Verhalten existiert noch nicht).
- [ ] **Step 4:** In `read_mvr` beim Befüllen von `embedded_files` ergänzen: Einträge überspringen, deren Name (nach `replace("\\\\","/")`) mit `/` beginnt, einen Doppelpunkt an Position 1 hat oder `..` als Pfadsegment enthält; `log.warning` je Skip.
- [ ] **Step 5:** Run → alle PASS. `ruff check .` sauber. Commit `feat: port hardened MVR reader with zip-traversal guard`.

### Task 4: gdtf.py portieren (Parsing, Scoring, Bibliothek, Kandidaten)

**Files:**
- Create: `mvr_enhancer/core/gdtf.py`, `tests/test_gdtf_matching.py`, `tests/test_gdtf_library.py`

**Interfaces:**
- Produces: `GdtfMode(name, channel_count)`, `GdtfFixture(manufacturer, name, revision, modes)`, `score_match(fixture_name, gdtf_name, manufacturer="") -> float`, `parse_gdtf(file_path) -> GdtfFixture|None`, `import_gdtf(file_path, library_dir) -> GdtfFixture|None`, `load_gdtf_library(library_dir, force_reload=False) -> dict[str, GdtfFixture]`, `invalidate_gdtf_cache()`, `find_all_gdtf_suggestions(fixture_names, gdtf_library, gdtf_overrides, *, top_n=5, threshold=0.3) -> dict[str, list[tuple[GdtfFixture, float]]]`, `find_gdtf_file(...) -> str|None`, `token_match(query, target) -> bool`, `MATCH_THRESHOLD = 0.6`.
- **Share-Client hier NICHT übernehmen** (kommt als `share.py` in Task 5) — beim Kopieren `GDTF_SHARE_BASE` + `class GdtfShareClient` + zugehörige Imports (`urllib`, `http.cookiejar`, `ssl`, `certifi`, `base64`) weglassen.

- [ ] **Step 1:** Kopieren `<SRC>/app/vectorwatch/parsing/gdtf.py` → `core/gdtf.py`; Imports anpassen; Share-Teile entfernen (Z. 376-539 der Quelle).
- [ ] **Step 2:** Änderung A — `find_all_gdtf_suggestions` bekommt Keyword-Parameter `top_n=5, threshold=0.3` (ersetzt die hartkodierten Werte in Quelle Z. 619/622).
- [ ] **Step 3:** Änderung B — `load_gdtf_library` scannt zusätzlich `.gdtf`-Dateien ohne JSON-Cache: nach dem JSON-Durchlauf `for f in os.listdir(...) if f.lower().endswith(".gdtf")`: wenn der von `parse_gdtf` gelieferte `fixture.name` noch nicht im Ergebnis-Dict ist → aufnehmen und via bestehender `_save_cache()` JSON-Cache erzeugen (damit Folge-Scans schnell sind). Defekte Dateien: `log.warning`, überspringen (auch wenn `parse_gdtf` None liefert — kein AttributeError wie im Alt-Bug `gdtf_library.py:630`).
- [ ] **Step 4:** Tests: `<SRC>/app/tests/test_gdtf_matching.py` übernehmen (Imports anpassen). Neu `tests/test_gdtf_library.py` mit builders: `test_scan_plain_gdtf_folder` (2 .gdtf ohne JSON → Bibliothek mit 2 Einträgen, JSON-Caches entstanden), `test_broken_gdtf_skipped` (Textdatei mit .gdtf-Endung → Bibliothek ohne Crash), `test_suggestions_sorted_and_thresholded` (Namen so wählen, dass Scores 1.0/0.7x/0.0 entstehen; threshold filtert, Sortierung absteigend, top_n greift), `test_suggestions_param_topn` (top_n=1 → 1 Kandidat).
- [ ] **Step 5:** Run → PASS. Commit `feat: port GDTF parsing/scoring/library with folder scan`.

### Task 5: share.py (GdtfShareClient)

**Files:**
- Create: `mvr_enhancer/core/share.py`, `tests/test_share.py`

**Interfaces:**
- Produces: `class GdtfShareClient` mit `login(username, password) -> bool`, `get_fixture_list(force_refresh=False) -> list[dict]` (cached; Dict-Felder wie API: rid, fixture, manufacturer, revision, modes[{name,dmxfootprint}], rating, uploader, filesize, creationDate), `search(query: str, limit=50) -> list[dict]` (clientseitig, `token_match` gegen `f"{manufacturer} {fixture}"`), `download(rid: int, library_dir: str) -> GdtfFixture|None`, `logout()`, Attribute `last_error: str`, `logged_in: bool`; Konstruktor `GdtfShareClient(cache_path: str | None = None)`.
- Consumes: `token_match`, `parse_gdtf`, `import_gdtf`, `invalidate_gdtf_cache` aus `core.gdtf`; `MAX_GDTF_DOWNLOAD_SIZE` aus `core.constants`.

- [ ] **Step 1:** Portieren aus `<SRC>/app/vectorwatch/parsing/gdtf.py` Z. 376-539 nach `core/share.py`; Basis `https://gdtf-share.com/apis/public`; Login als Form-POST (`urllib.parse.urlencode`); Session-Cookies via `http.cookiejar.CookieJar` + `urllib.request.build_opener(HTTPCookieProcessor)`; certifi-Kontext in `try/except ImportError`; 401 → einmaliger Relogin (`_retry_active`-Guard); Download chunked mit Größenabbruch, `os.path.basename` auf Content-Disposition. Zusätzlich beheben (Alt-Defekt): jeder `except`-Pfad in `download` endet mit explizitem `return None`; `dest` vor `try` initialisieren. Listen-Cache: `get_fixture_list` schreibt/liest `cache_path` (JSON `{timestamp, list}`), `force_refresh=True` erzwingt Netz.
- [ ] **Step 2:** `tests/test_share.py` — HTTP mocken via `monkeypatch` auf die interne Request-Funktion (`GdtfShareClient._request(method, slug, params=None, data=None) -> tuple[int, bytes]` als einzige Netz-Stelle designen!): `test_login_success_sets_state`, `test_login_failure_sets_error` (401-Antwort), `test_search_filters_and_limits` (Liste mit 3 Einträgen, Query matcht 2, limit=1), `test_download_writes_and_imports` (bytes einer builder-GDTF zurückgeben → Datei in library_dir, Rückgabe GdtfFixture), `test_download_size_limit` (Antwort > monkeypatchtem Limit → None + last_error), `test_list_cache_roundtrip` (2. Aufruf ohne Netz-Mock-Treffer).
- [ ] **Step 3:** Run → PASS. Commit `feat: GDTF Share client (login, cached list, search, download)`.

### Task 6: models.py (UI-Datenmodelle)

**Files:**
- Create: `mvr_enhancer/core/models.py`, `tests/test_models.py`

**Interfaces:**
- Produces (exakt diese Namen/Felder; alle Dataclasses mit `to_dict()` via `dataclasses.asdict`-Helper `serialize(obj) -> dict`):
```python
@dataclass
class FixtureType:
    key: str            # normalisierter Name (core.gdtf._normalize)
    name: str           # Anzeigename (häufigster Original-Name)
    count: int
    positions: list[str]
    meta_line: str      # z. B. "24× · Traverse 1–3" bzw. "24× · ohne Position"
    existing_spec: str  # GDTFSpec aus dem MVR, "" wenn leer
    existing_mode: str

@dataclass
class Candidate:
    gdtf_name: str      # Dateiname/Fixture-Name in Bibliothek
    manufacturer: str
    revision: str
    score: float
    modes: list[dict]   # [{"name": str, "channel_count": int}]
    source: str         # "library" | "share"

@dataclass
class Assignment:
    gdtf_name: str | None = None   # None = offen; "" nie verwenden
    mode_name: str | None = None
    removed: bool = False          # True = Typ wird aus Export entfernt
    mode_is_fallback: bool = False
    source: str = "library"

@dataclass
class MvrStats:
    fixtures: int; fixture_types: int; meshes: int; positions: int

@dataclass
class ModeFallbackWarning:
    type_name: str; count: int; gdtf_name: str; mode_name: str

@dataclass
class CollisionWarning:
    universe: int; start: int; end: int; fixture_names: list[str]

@dataclass
class CleanupSummary:
    removed_fixture_count: int
    removed_type_names: list[str]
    orphan_gdtf_names: list[str]
    stripped_tag_counts: dict[str, int]   # {"CustomCommands": 12, "Position": 12}

@dataclass
class EnrichReport:
    matched_fixtures: int; total_fixtures: int
    embedded_gdtf_count: int; mesh_count: int; position_group_count: int
    fallbacks: list[ModeFallbackWarning]
    cleanup: CleanupSummary

@dataclass
class EnrichResult:
    data: bytes
    report: EnrichReport
```
- [ ] **Step 1:** Test: `serialize(EnrichReport(...))` liefert verschachteltes Dict ohne bytes-Probleme; `Assignment()`-Defaults. Dann implementieren, Run → PASS. Commit `feat: UI-facing core data models`.

### Task 7: analysis.py (Typ-Aggregation, Positionen, Stats, Kollisionen)

**Files:**
- Create: `mvr_enhancer/core/analysis.py`, `tests/test_analysis.py`

**Interfaces:**
- Consumes: `MvrScene`/`MvrFixture` (Task 3), `_normalize` aus `core.gdtf`, Models (Task 6).
- Produces:
  - `parse_position_names(scene: MvrScene) -> dict[str, str]` — UUID→Name aus `AUXData/Positions/Position` (Attribute `uuid`, `name`); leeres Dict wenn kein AUXData.
  - `aggregate_fixture_types(scene: MvrScene) -> list[FixtureType]` — Gruppierung nach `_normalize(fixture.name)`; `positions`: sortierte eindeutige Positionsnamen der Instanzen (Fixture-`<Position>`-Kind-UUID → Name via parse_position_names; Fallback: Name des Layers, in dem das Fixture liegt; sonst „ohne Position"); `meta_line`: `f"{count}× · {', '.join(positions[:3])}"` + `" …"` falls >3.
  - `compute_stats(scene: MvrScene, types: list[FixtureType]) -> MvrStats` — meshes = Anzahl embedded_files mit Endung in `{.glb,.3ds,.gltf,.obj,.fbx}` (case-insensitiv), positions = eindeutige Positionsnamen ≠ „ohne Position".
  - `detect_address_collisions(scene: MvrScene, types: list[FixtureType], assignments: dict[str, Assignment], footprints: dict[str, int]) -> list[CollisionWarning]` — `footprints`: type_key → channel_count des gewählten Modus. Je Fixture-Instanz Intervall `[addr, addr+footprint-1]` (absolut); pro Universum (`divmod(addr-1,512)`) Überlappungen melden; entfernte Typen (`removed`) und Typen ohne Assignment auslassen; ein `CollisionWarning` je Überlappungspaar-Cluster mit 1-basierten Kanalangaben im Universum.
- **Hinweis:** `MvrFixture` hat kein Positions-/Layer-Feld — `aggregate_fixture_types` liest das Position-Kind direkt aus `fixture.element` (`element.find("Position")`, dessen Text = UUID) und die Layer-Zugehörigkeit über eine beim Lesen aufgebaute Map. Dafür `read_mvr` NICHT ändern; stattdessen in analysis über `scene.xml_root.iter()` Layer→Fixture-UUIDs einsammeln (`Layer`-Attribut `name`, drin enthaltene `Fixture`-`uuid`-Attribute).

- [ ] **Step 1:** Tests mit builders: `test_aggregate_groups_by_name` (2 Typen aus 5 Fixtures, counts stimmen), `test_positions_from_auxdata` (aux_positions gesetzt → meta_line enthält Positionsname), `test_position_fallback_layer` (ohne AUXData → Layer-Name), `test_stats_counts` (fixtures/types/meshes/positions), `test_collision_detected` (2 Fixtures Uni 4 Kanal 12+, Footprints überlappen → 1 Warnung mit universe=4), `test_no_collision_when_removed` (removed=True → leer).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. **Step 4:** Run → PASS. Commit `feat: MVR analysis (type aggregation, positions, stats, collisions)`.

### Task 8: enricher.py (typ-basiert, Orphan-Cleanup, Report)

**Files:**
- Create: `mvr_enhancer/core/enricher.py`, `tests/test_enricher.py`

**Interfaces:**
- Consumes: `MvrScene` (Task 3), `load_gdtf_library`/`find_gdtf_file`/`GdtfFixture` (Task 4), Models (Task 6), `aggregate_fixture_types` (Task 7).
- Produces: `enrich_mvr(scene: MvrScene, types: list[FixtureType], assignments: dict[str, Assignment], gdtf_library_dir: str, gdtf_library: dict[str, GdtfFixture], group_by_position: bool = True) -> EnrichResult`.
- Portierungsquelle: `<SRC>/app/vectorwatch/parsing/mvr_enricher.py` — Logik übernehmen, aber: kein `Fixture`-Import, kein `_match_fixtures`; Zuordnung läuft `MvrFixture → type_key (via _normalize(name)) → assignments[type_key]`.

- [ ] **Step 1:** Tests (Roundtrip mit builders, Export-bytes wieder mit `read_mvr` über Temp-Datei einlesen):
  - `test_poison_elements_stripped` — poison-MVR → Ergebnis-XML ohne `CustomCommands`/`Position`; `report.cleanup.stripped_tag_counts` gezählt.
  - `test_removed_type_dropped` — Assignment removed=True → Fixtures fehlen im Ergebnis, `removed_type_names` + `removed_fixture_count` gesetzt.
  - `test_orphan_gdtf_removed` — embedded `Orphan@Old@r0.gdtf` ohne Referenz → nicht im Ergebnis-ZIP, in `orphan_gdtf_names` gelistet; Meshes (`mesh1.glb`) bleiben erhalten.
  - `test_assigned_gdtf_embedded_and_spec_set` — Bibliotheks-GDTF zugewiesen → ZIP enthält Datei, Fixture-`GDTFSpec` gesetzt, `GDTFMode` = gewählter Modus.
  - `test_mode_fallback_reported` — Assignment ohne mode_name, GDTF hat Modi → `modes[0]` verwendet, `fallbacks` enthält Warnung mit count.
  - `test_reproducible_uuids` — zwei Läufe → identische Layer/Group-UUIDs.
  - `test_grouping_by_position` — group_by_position=True → GroupObjects je Position; False → ein flacher Layer.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren: `_STRIP_TAGS`, `_clean_gdtf_name`, `_update_fixture_element`, `_reorganize_layers` aus Quelle übernehmen/anpassen (Layer-Name „MVR Enhancer Export"); danach Referenz-Set aller finalen `GDTFSpec`-Werte (URL-dekodiert, mit/ohne `.gdtf`-Endung normalisiert) bilden und nur referenzierte GDTFs in den ZIP schreiben; Report befüllen. **Step 4:** Run → PASS, `ruff` sauber. Commit `feat: type-based enricher with orphan cleanup and structured report`.

## Phase C — App-Schicht

### Task 9: settings.py + winsec.py (Persistenz, DPAPI)

**Files:**
- Create: `mvr_enhancer/settings.py`, `mvr_enhancer/winsec.py`, `tests/test_settings.py`, `tests/test_winsec.py`

**Interfaces:**
- Produces: `class Settings` mit `load() -> Settings` (classmethod), `save()`, Feldern `recent_files: list[dict]` (`{path, ts}` max 5, neueste zuerst, `add_recent(path)` dedupliziert), `gdtf_library_dir: str`, `last_export_dir: str`, `group_by_position: bool = True`, `share_user: str`, `share_password_enc: str`; Pfad `%APPDATA%/MVR Enhancer/config.json` (überschreibbar via Konstruktor-Arg `base_dir` für Tests), atomares Schreiben (`tempfile.mkstemp` + `os.replace`). `winsec.encrypt_password(str) -> str` / `decrypt_password(str) -> str` (DPAPI via ctypes, portiert aus `<SRC>/app/vectorwatch/win_platform.py:67-99`; auf Nicht-Windows: ValueError).
- [ ] **Step 1:** Tests: Roundtrip save/load, add_recent-Dedupe+Limit, korruptes JSON → Defaults, `test_winsec_roundtrip` (skipif nicht win32). **Step 2:** FAIL → implementieren → PASS. Commit `feat: settings persistence and DPAPI password storage`.

### Task 10: api.py + main.py (Bridge, Zustand, Fenster)

**Files:**
- Create: `mvr_enhancer/api.py`, `mvr_enhancer/main.py`, `tests/test_api.py`
- Modify: `mvr_enhancer/__main__.py` (Inhalt: `from mvr_enhancer.main import run; run()` unter `if __name__ == "__main__":`)

**Interfaces:**
- Consumes: alles aus Phase B/C.
- Produces: `class Api` — **alle** Methoden geben `{"ok": bool, "data": …}` bzw. `{"ok": False, "error": str}` zurück; Zustand liegt in `Api._state` (Python = Single Source of Truth). Methoden:
  - `get_state()` → kompletter UI-Zustand: `{mvr_loaded, file_meta:{name,path,size_mb,modified}, stats, types:[{…FixtureType, candidates:[Candidate], assignment:{…}}], grouping, share:{logged_in, user}, library:{dir, count}, recent:[{path,name,ts}], warnings:{fallbacks:[], collisions:[], cleanup_preview}, export:{done, path, size_mb, time, default_path}, assigned_count, open_count}`
  - `choose_mvr()` (webview `create_file_dialog` OPEN, Filter `*.mvr`) → lädt via `load_mvr`.
  - `load_mvr(path)` — synchron im Worker: `read_mvr` → `aggregate_fixture_types` → `load_gdtf_library` → `find_all_gdtf_suggestions`; Auto-Assignment: bester Kandidat mit Score ≥ `MATCH_THRESHOLD` (0.6) wird vorbelegt (Modus: Substring-Match `existing_mode` ↔ GDTF-Modi, sonst `modes[0]` + `mode_is_fallback=True`); Typen deren Name „plugbox"/„verteiler" enthält oder `existing_spec == ""` und 0 Kandidaten → bleiben offen (KEIN Auto-remove; Nutzer entscheidet). Persistiert recent.
  - `remove_mvr()`, `set_active_step(n)` (nur für Fenster-Titel-Logik, UI hält Akkordeon lokal), `set_gdtf(type_key, gdtf_name)` (setzt candidates-Quelle, resettet Modus auf besten Match), `set_mode(type_key, mode_name)`, `set_removed(type_key, flag)`, `set_grouping(flag)`.
  - `choose_library_dir()` (FOLDER-Dialog) + `rescan_library()` → aktualisiert Kandidaten aller offenen Typen.
  - `share_login(user, password, remember)`, `share_logout()`, `share_search(query)`, `share_download(rid, type_key)` → importiert + setzt Assignment des Typs (source="share").
  - `prepare_export()` → `warnings` (fallbacks aus Assignments, collisions via `detect_address_collisions`, cleanup_preview via Trockenlauf-Zählung: offene Typen + removed-Typen → zu entfernende Fixture-Zahl, verwaiste GDTFs = embedded .gdtf ohne Referenz durch aktuelle Assignments/verbleibende Specs), `default_path` = `last_export_dir` oder MVR-Ordner + `<name>_MA3.mvr`.
  - `run_export(path="")` — leerer Pfad → SAVE-Dialog; ruft `enrich_mvr` (offene Typen zählen als removed — Handoff: „Nicht zugeordnete Typen werden entfernt — das ist gewollt"); schreibt Datei; Rückgabe `{path, size_mb, time_str, report}`.
  - `reset_export()` — setzt `export.done=False` zurück (MVR + Assignments bleiben; für „Neuen Export starten").
  - `open_folder(path)` (`os.startfile` auf Ordner), `get_version()` → "0.1.0".
- `main.run()`: `webview.create_window("Groh·PA MVR Export", url=<ui/index.html>, js_api=Api(), width=1280, height=1036, min_size=(1100, 800))`; nach Laden/Entfernen Titel „Groh·PA MVR Export — <datei>" via `window.set_title`. `webview.start()` ohne debug im Release; `MVR_ENHANCER_DEBUG=1` env → `debug=True`.
- Lange Operationen (`load_mvr`, `rescan_library`, `share_*`, `run_export`): in `threading.Thread`; Fertig-Meldung per `window.evaluate_js(f"app.onEvent({json})")` mit Events `{type: "state"|"toast"|"progress", …}`. Für Tests ist die Thread-Nutzung abschaltbar: `Api(sync=True)`.

- [ ] **Step 1:** Tests (Api mit `sync=True`, Dialoge/webview-Objekte gemockt): `test_load_mvr_populates_state` (builders-MVR + Bibliothek → types mit candidates, auto-assignment bei Score 1.0, assigned_count korrekt), `test_set_gdtf_and_mode`, `test_set_removed_affects_cleanup_preview`, `test_prepare_export_warnings` (Fallback + eine Kollision), `test_run_export_writes_file_and_report` (Datei existiert, `report.matched_fixtures` stimmt, exportiert-Flag in state), `test_recent_persisted` (Settings-Datei), `test_share_login_updates_state` (Share-Client gemockt).
- [ ] **Step 2:** FAIL → implementieren → PASS. `python -m mvr_enhancer` startet (manueller Smoke: Fenster erscheint — Platzhalter-index.html mit „MVR Enhancer" reicht in dieser Task; echte UI folgt Phase D). Commit `feat: pywebview bridge, app state and window entry point`.

## Phase D — Frontend

### Task 11: UI-Assets (Tokens, Fonts, Icons, Bild)

**Files:**
- Create: `mvr_enhancer/ui/css/tokens.css`, `mvr_enhancer/ui/assets/fonts/*.woff2` + `fonts.css`, `mvr_enhancer/ui/assets/icons.js`, `mvr_enhancer/ui/assets/hintergrund.jpg`
- Create: `tools/fetch_assets.py` (einmalig ausgeführt, committed für Reproduzierbarkeit)

**Interfaces:**
- Produces: `tokens.css` = Inhalt von `design_handoff_mvr_export_tool/design_system/tokens/{colors,typography,spacing,effects}.css` konkateniert (OHNE fonts.css-Google-Import); `fonts.css` mit `@font-face`-Regeln auf lokale woff2; `icons.js` mit `const ICONS = {name: '<svg …>'}` für exakt: settings-2, upload, file-box, shield-check, box, link-2, eraser, folder-open, globe, info, check, arrow-down-to-line, triangle-alert, zap, list-checks, circle-check, x, search, log-in (x/search/log-in zusätzlich für Modals) — Quelle `https://unpkg.com/lucide-static@0.469.0/icons/<name>.svg`, `stroke-width` auf 2 belassen.
- [ ] **Step 1:** `tools/fetch_assets.py`: lädt (a) die 19 Lucide-SVGs und schreibt `icons.js`; (b) Google-Fonts-CSS mit Chrome-UA für die Familien/Weights aus `design_handoff_mvr_export_tool/design_system/tokens/fonts.css:5` (Barlow 400,500,600,700 + 400italic; Barlow Condensed 500,600,700; Barlow Semi Condensed 500,600; JetBrains Mono 400,500; jeweils latin + latin-ext), lädt die woff2 und schreibt `fonts.css` mit relativen `url()`.
- [ ] **Step 2:** Skript ausführen; `hintergrund.jpg` aus `design_handoff_mvr_export_tool/assets/backgrounds/` kopieren; tokens.css konkatenieren. Prüfen: keine `http`-Referenzen in `mvr_enhancer/ui/` (`grep -r "https\?://" mvr_enhancer/ui/` → nur ggf. SVG-xmlns).
- [ ] **Step 3:** Commit `feat: bundle offline UI assets (tokens, fonts, lucide icons, background)`.

### Task 12: index.html + app.css (statisches Layout aller Schritte)

**Files:**
- Create: `mvr_enhancer/ui/index.html`, `mvr_enhancer/ui/css/app.css`

**Interfaces:**
- Produces: komplette DOM-Struktur mit stabilen IDs/Klassen, die `app.js` (Task 13) befüllt: `#app` (flex column, `height:100vh; overflow:hidden`), `#header`, `#sect-1/2/3` (Grid `88px minmax(0,1fr)`, gap 20px, max-width 1240px), Rail-Knoten `#node-1/2/3`, Inhalts-Wrapper `#wrap-1/2/3` + Zoom `#zoom-1/2/3`, `#dropzone`, `#filecard`, `#recent-list`, `#sources-bar`, `#match-table`, `#export-stats`, `#warn-stack`, `#export-panel`, `#report-banner`, `#footer`, Modals `#modal-share-login`, `#modal-share-search`.
- **Pflichtlektüre für den Implementierer:** `design_handoff_mvr_export_tool/README.md` KOMPLETT + Spec §5. Alle Copy-Texte wörtlich aus dem Handoff.

Kernwerte (Auszug — Details stehen im Handoff; bei Konflikt gilt diese Liste, sie enthält die Prototyp-Korrekturen):
- Header 56px `--navy-950`, Padding 0 28px; Wordmark „GROH·PA" Barlow Condensed 700 22px ls 0.06em; Trenner 1×22px `--border-dark`; „MVR EXPORT" Barlow Semi Condensed 600 15px uppercase `--blue-300`; rechts JetBrains Mono 11px `v0.1.0 · DIN SPEC 15801 · MVR 1.6` + settings-2 18px.
- Akkordeon: Sektion `transition: flex-grow 520ms cubic-bezier(0.16,1,0.3,1)`; aktiv S1 `flex:0 0 auto`(!), S2/S3 `flex:1 1 auto`; Wrapper `max-height` 0↔900px gleiche Kurve; Zoom `scale(0.96) translateY(-14px)`→`scale(1)`, `transform 520ms cubic-bezier(0.16,1,0.3,1), opacity 360ms ease`, origin top left. Titel-`font-size`-Transition 420ms; S1 aktiv 40px / S2 S3 32px / kollabiert 21px; ls 0.02em; S1 line-height 1.05. Eyebrows Mono 11px ls 0.14em `--blue-300`.
- Rail: Knoten 44×44 rund, Barlow Condensed 700 19px weiß; aktiv `--blue-600` + `--shadow-brand`, Transition `background 320ms, box-shadow 320ms` (Default-ease); inaktiv `--navy-700` Border `rgba(255,255,255,0.18)`; fertig: check-Icon 20px `--blue-300`, Border `--blue-400`; Knoten 3 arrow-down-to-line; Linien 2px `rgba(255,255,255,0.16)` — S1 nur unterhalb (margin-top 8px), S2 32px oberhalb + flex unterhalb, S3 nur 32px oberhalb.
- S1-BG: `linear-gradient(180deg,rgba(8,19,31,0.60),rgba(8,19,31,0.92)), url(../assets/hintergrund.jpg)` cover/center; Raster-Padding `36px 24px 0`, Inhalt `padding-bottom:28px`. Dropzone/Dateikarte/Grids exakt nach Handoff §Schritt 1.
- S2 `--navy-900`, Raster `0 24px`, Inhalt pt 32 pb 28; Quellen-Leiste, Tabelle (Grid `minmax(190px,1.2fr) minmax(230px,1.6fr) 84px minmax(180px,1.1fr) 120px`, sticky Header 10.5px ls 0.12em bg `--navy-900`, Zeilen 10px 20px, min-width 900px, Container `overflow:auto; flex:1 1 auto; min-height:120px`), Fußnote, Primärbutton.
- Dunkles Select (eigene Klasse `.sel-dark`): bg `--navy-900`, Border `rgba(255,255,255,0.25)`, `color:#fff`, Radius 3px, Padding 11px 40px 11px 14px, `appearance:none` + heller Chevron als background-SVG, `color-scheme:dark`.
- S3 `--navy-950`, Grid `minmax(0,1fr) 340px` gap 20, Inhalt `overflow-y:auto` pt 20; Stat-Werte Barlow Condensed 700 (App-Größe 26px in Dateikarte, Stats im S3 nach Stat-Komponente: Wert `--blue-300`, Label 13px/600 ls 0.14em uppercase `--text-inverse-muted`); Warnzeilen amber/rot/neutral nach Handoff; Export-Panel 340px.
- Buttons: Basis uppercase Barlow Semi Condensed 600 ls 0.14em Radius 3px Border 2px transparent; sm 13px/8-16px h36, md 15px/11-22px h44, lg 17px/15-30px h54; primary #1e7cc4→hover `--blue-700`→press `--blue-800` transform 120ms; onDarkOutline transparent Border `rgba(255,255,255,0.5)`, hover Border #fff bg `rgba(255,255,255,0.06)`.
- Badges: 12px/600 ls 0.14em uppercase, 4px 10px, Radius 3px, line-height 1; onDark `rgba(255,255,255,0.14)`/#fff; brand `#eaf4fb`/`#145a96`; success `#e4f4ec`/`#2f9e6e`; warning `#fbf0da`/`#a9740f`; danger `#fbe4e4`/`#d64545`.
- Checkbox onDark: 20×20 Radius 3 Border 2 `rgba(255,255,255,0.4)`; checked bg+Border `--brand-primary`, SVG-Häkchen 12×12 sw 3.5; Label 15px #fff.
- Karten: `--surface-card-dark`, 1px `--border-dark`, Radius 10px (Paddings je Karte laut Handoff: Dateikarte 20px 24px, Quellen-Leiste 14px 20px, Info-Karten 18px 20px, Export-Panel 20px).
- Footer: `margin-top:auto; padding:14px 28px`, 12px muted, Top-Border; links „GROH·PA · Veranstaltungstechnik · Buchholz i.d.N.", rechts Mono „grandMA3-geprüfte Pipeline".
- Modals (neu, Design-System-Stil): Overlay `rgba(8,19,31,0.7)`; Karte dark, Radius 10px, max-width 480px (Login) / 640px (Suche, Ergebnisliste intern scrollend max-height 400px); Titel Barlow Condensed 700 24px uppercase; Inputs wie `.sel-dark` ohne Chevron; Schließen-x oben rechts.

- [ ] **Step 1:** `index.html` + `app.css` bauen; alle drei Sektionen im „geladenen" Beispielzustand hart sichtbar (statisch, ohne JS) zum visuellen Abgleich.
- [ ] **Step 2:** Verifikation: `python -m mvr_enhancer` (oder Browser-Öffnen der Datei) + Screenshot; Abgleich gegen `design_handoff_mvr_export_tool/MVR Export App.dc.html`-Beschreibung — Prüfliste: Headerhöhe, Knotenfarben, Tabellen-Grid, Badge-Farben, Footer.
- [ ] **Step 3:** Commit `feat: static UI layout for all three steps`.

### Task 13: app.js (Zustand, Rendering, Interaktion, Bridge)

**Files:**
- Create: `mvr_enhancer/ui/js/app.js`
- Modify: `mvr_enhancer/ui/index.html` (Script-Tags: icons.js, app.js)

**Interfaces:**
- Consumes: `window.pywebview.api.<methode>()` (Task 10; alle async, Rückgabe `{ok, data|error}`), `ICONS` (Task 11), DOM-IDs (Task 12).
- Produces: globales `app`-Objekt mit `app.onEvent(evt)` (von Python gerufen: `{type:"state", state}` → re-render; `{type:"toast", level, text}`; `{type:"progress", text}`).

Verhalten (Handoff §Interactions + Prototyp-Analyse):
- Lokaler UI-State: `aktiv (1|2|3)`, `nurProbleme (bool)`; alles andere kommt aus `get_state()`.
- `f1 = mvr_loaded`, `f2 = mvr_loaded && (aktiv===3 || export.done)`, `f3 = export.done`; Kopf-Klick → `aktiv=n` (immer erlaubt; ohne MVR zeigen S2/S3 Wartezustand „wartet auf Quell-MVR"/„wartet auf Matching").
- MVR geladen → nach 750ms Auto-Advance zu Schritt 2 (Timer bei „Entfernen" abbrechen, `stopPropagation`).
- Dropzone: Klick → `choose_mvr()`; dragover/leave Hover-Stil; drop → `e.dataTransfer.files[0]` → `load_mvr(f.pywebviewFullPath ?? f.name)` (wenn kein Pfad auflösbar → Toast „Bitte über den Dialog wählen").
- Tabelle rendert aus `state.types`: Select GDTF (Kandidaten, `selected` = assignment.gdtf_name; Option-Label = `gdtf_name` mit Score im Text NICHT — Score hat eigene Spalte); Score-Badge (`toFixed(2)`, Farben laut Schwellen, ohne Score En-Dash-Badge onDark); Modus-Select (+ FALLBACK-Label amber 11px/600 uppercase mit title-Tooltip „Fallback: erster Modus der GDTF"); Quelle-Badge Bibliothek/Share/offen/entfernt; kein Kandidat → „kein Treffer in der Bibliothek" + Button „Im Share suchen" (öffnet Such-Modal mit Typ-Name als Query); removed → durchgestrichen „wird entfernt" + „Doch zuordnen"; Problemzeilen (offen || fallback) bg `rgba(92,174,221,0.08)`; Meta-Zeile Mono 11.5px.
- Badge neben S2-Titel: `${assigned} von ${total} zugeordnet` berechnet; Kollabiert-Summaries dynamisch: S1 `<datei> · N Fixtures · M Meshes`/„noch keine Datei geladen"; S2 `X von Y Typen zugeordnet · Z offene Punkte`/„wartet auf Quell-MVR"; S3 `exportiert · <zeit>`/`bereit · N Warnungen`/„wartet auf Matching".
- Filter-Toggle „nur Probleme" über der Tabelle (Checkbox onDark, filtert `!ok`-Zeilen inkl. entfernter).
- Quellen-Leiste: Bibliothekspfad klickbar → `choose_library_dir()`; Share-Status (grüner 7px-Punkt + „angemeldet als <user>" + abmelden-Link | „nicht angemeldet" + „Anmelden"-Button → Login-Modal); Checkbox „Nach Position gruppieren" → `set_grouping`; „Overrides teilen" Button disabled (title „folgt in einem späteren Release").
- „Weiter: Export vorbereiten" → `prepare_export()` → `aktiv=3`.
- S3: Stats (matched/total, embedded GDTFs, Meshes, Positionsgruppen); Warn-Stack amber (je Fallback-Typ: `**N× Modus-Fallback:** <Typ> nutzt den ersten Modus der GDTF — bitte in Schritt 2 prüfen.`), rot (je Kollision: `**Adress-Kollision:** Universum U, Kanal A–B doppelt belegt (<fixtures>).`), neutral Bereinigungsliste; Export-Button: 0 Warnungen → primary „Exportieren", sonst amber (bg+border `--amber-500`, Text `--navy-950`) „Mit N Warnungen exportieren" → `run_export("")`; Erfolgsansicht mit Report-Banner, „Ordner öffnen" → `open_folder`, „Diff zum letzten Export" disabled, „Neuen Export starten" → Reset exportiert (Backend: state.export.done=false via `set_removed`?-NEIN: eigene Api-Methode `reset_export()` — in Task 10 bereits vorsehen!).
- Icons: `el.innerHTML = ICONS[name]` — kein Lucide-JS-Runtime.

- [ ] **Step 1:** `app.js` implementieren (render() je Sektion, Event-Delegation, Akkordeon-Klassen togglen).
- [ ] **Step 2:** Manueller Durchlauf mit echter Mini-Bibliothek + builder-MVR (Skript `tools/make_demo_data.py` schreiben: erzeugt `demo/` mit 3 GDTFs + 1 MVR aus tests/builders): laden → matchen → exportieren → Report; Ergebnis-MVR mit `read_mvr` gegenprüfen.
- [ ] **Step 3:** Commit `feat: interactive UI wired to python bridge`.

### Task 14: Design-Review gegen Prototyp

**Files:** keine neuen (Fix-Commits erlaubt)

- [ ] **Step 1:** App mit Demo-Daten starten, Screenshots aller Zustände (S1 leer/geladen, S2 Tabelle, S3 vor/nach Export, Modals) — z. B. via `webview`-Fenster + Snipping oder `window.evaluate_js` + `html2canvas` NICHT nötig: einfach OS-Screenshot.
- [ ] **Step 2:** Punkt-für-Punkt-Abgleich gegen `design_handoff_mvr_export_tool/README.md` (Checkliste: Farben #1e7cc4/#5caedd/#e5a32b/#d64545, Typo-Größen 40/32/21, Akkordeon-Timings, Tabellen-Spalten, Badge-Töne, Score-Schwellen, Copy-Texte wörtlich, Footer). Abweichungen fixen, je Fix ein Commit `fix(ui): …`.
- [ ] **Step 3:** Commit/Abschluss `docs: design review notes` (kurze Notiz `docs/design-review.md`, was geprüft/abgewichen).

## Phase E — Packaging & Release

### Task 15: PyInstaller-Build lokal

**Files:**
- Create: `build/pyinstaller.spec`, `tools/build_exe.ps1`

**Interfaces:**
- Produces: `dist/MVR Enhancer.exe` (onefile, windowed).

- [ ] **Step 1:** Spec: `Analysis(['../mvr_enhancer/__main__.py'], datas=[('../mvr_enhancer/ui', 'mvr_enhancer/ui')], hiddenimports=['pygdtf','certifi','defusedxml','webview.platforms.edgechromium'])`; `EXE(..., name='MVR Enhancer', console=False)`. UI-Pfad-Auflösung in `main.py` frozen-fähig machen: `base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))` → `base / "mvr_enhancer" / "ui" / "index.html"` (in Task 10 bereits so implementieren; hier verifizieren).
- [ ] **Step 2:** `tools/build_exe.ps1`: `.venv\Scripts\pyinstaller build\pyinstaller.spec --noconfirm --distpath dist`. Ausführen.
- [ ] **Step 3:** Smoke: `dist/MVR Enhancer.exe` starten → Fenster mit UI erscheint; Demo-MVR laden → Export durchläuft. (Manuelle Verifikation, Ergebnis im Commit-Text dokumentieren.)
- [ ] **Step 4:** Commit `build: pyinstaller onefile spec and build script`.

### Task 16: Release-Workflow (GitHub Actions)

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1:** Workflow: `on: push: tags: ['v*']`; `runs-on: windows-latest`; Schritte: checkout, setup-python 3.12, `pip install -e .[dev]`, `ruff check .`, `pytest -q`, `pyinstaller build/pyinstaller.spec --noconfirm --distpath dist`, `softprops/action-gh-release@v2` mit `files: "dist/MVR Enhancer.exe"`, `generate_release_notes: true`, `permissions: contents: write`.
- [ ] **Step 2:** Commit + push; CI (ci.yml) grün abwarten (`gh run watch`).
- [ ] **Step 3:** Commit `ci: release workflow building windows exe on tag`.

### Task 17: Release v0.1.0

- [ ] **Step 1:** README.md des Repos ausfüllen (Was ist MVR Enhancer, Screenshot, Download-Hinweis auf Releases, WebView2-Voraussetzung, Entwicklung: pip install -e, pytest, build).
- [ ] **Step 2:** `git tag v0.1.0 && git push origin main --tags`; `gh run watch` bis Release-Workflow grün; `gh release view v0.1.0` → .exe-Asset vorhanden.
- [ ] **Step 3:** Release-Notes prüfen/ergänzen: Features, bekannte Grenzen (Backlog: Score-Legende, Kollisions-Detailansicht, Overrides teilen, Diff), WebView2-Hinweis.
