# MVR Enhancer — Design-Dokument

**Datum:** 2026-08-05 · **Repo:** `Harlekin7/mvr-enhancer` · **Status:** beschlossen (Rückfragen beantwortet am 2026-08-05)

## 1. Ziel & Scope

Eigenständige Windows-Desktop-App für Lichtdesigner: Ein aus Vectorworks exportiertes MVR wird geladen, jedem Fixture-Typ wird eine konkrete GDTF-Datei + DMX-Modus zugeordnet (Score-basierte Vorschläge, Nutzer hat das letzte Wort), und ein bereinigtes, grandMA3-sicheres MVR wird exportiert.

**Beschlossene Eckpunkte (Nutzer-Antworten):**
1. Backend-Module werden aus `Harlekin7/Vectorworks-Tool-GPA` (Branch `m1-5-ui-smoke`) **portiert** (kopiert und als eigenständiges Paket angepasst).
2. UI-Stack: **pywebview** (HTML/CSS/JS-Frontend in nativem Fenster) + **PyInstaller** für die .exe.
3. Release: **lokaler Build zum Verifizieren + GitHub-Actions-Workflow**, Veröffentlichung als GitHub Release `v0.1.0`.
4. Funktionsumfang v1: **voll funktionsfähig inkl. GDTF Share** (Login, Suche, Download) und lokaler GDTF-Bibliothek (Ordner wählbar, wird gescannt).

**Nicht in v1** (Backlog laut Handoff): Score-Legende-Tooltip, Detailansicht der Adress-Kollision, „Overrides teilen"-Funktion (Button vorhanden, ohne Funktion), Diff zum letzten Export (Button vorhanden, ohne Funktion).

## 2. Architektur

Ein Python-Paket, ein Prozess. pywebview zeigt ein natives Fenster (Client-Area 1280×1000, Minimum) mit einem lokalen HTML/CSS/JS-Frontend; Backend-Aufrufe laufen über die pywebview `js_api`-Bridge.

```
mvr-enhancer/
├── mvr_enhancer/
│   ├── __init__.py            # __version__
│   ├── __main__.py            # python -m mvr_enhancer
│   ├── main.py                # webview.create_window(..., js_api=Api), 1280×1000
│   ├── api.py                 # Api-Klasse: JS↔Python-Bridge (alle UI-Operationen)
│   ├── core/
│   │   ├── constants.py       # MVR-/GDTF-Limits (portiert)
│   │   ├── mvr_reader.py      # read_mvr → MvrScene (portiert + Härtung)
│   │   ├── gdtf.py            # Parsing, Bibliothek, Scoring, Kandidaten (portiert)
│   │   ├── share.py           # GdtfShareClient (portiert aus gdtf.py, eigenes Modul)
│   │   ├── analysis.py        # NEU: Typ-Aggregation, Positionen, Stats, Kollisionen
│   │   ├── enricher.py        # REFACTORED: typ-basiertes Enrichment + EnrichReport
│   │   └── models.py          # Dataclasses: FixtureType, Assignment, Stats, Warnungen, Report
│   ├── settings.py            # Persistenz: %APPDATA%/MVR Enhancer/config.json (atomar)
│   ├── winsec.py              # DPAPI encrypt/decrypt für Share-Passwort (portiert)
│   └── ui/                    # statische Web-Assets (offline, keine CDNs)
│       ├── index.html
│       ├── css/  (tokens.css aus design_system übernommen, app.css)
│       ├── js/   (app.js — Vanilla JS, kein Framework)
│       └── assets/ (hintergrund.jpg, gebündelte Fonts woff2, Lucide-SVGs inline)
├── tests/                     # pytest; MVR/GDTF-Fixtures programmatisch erzeugt
├── build/pyinstaller.spec     # onedir→onefile windowed Build
├── .github/workflows/release.yml
├── pyproject.toml             # deps: pywebview, pygdtf, defusedxml, certifi; dev: pytest, ruff, pyinstaller
└── docs/superpowers/…         # Spec + Plan
```

**Begründung Stack-Wahl:** Backend ist Python (portierte Module); pywebview vermeidet eine zweite Toolchain (Node/Rust), die Design-CSS-Werte übertragen sich 1:1, und PyInstaller erzeugt eine einzelne .exe. Auf Windows nutzt pywebview WebView2 (Edge/Chromium, auf Win11 vorinstalliert).

**Alternativen erwogen:** Tauri+React (kleinere .exe, aber Rust+Node-Toolchain und Sidecar-Komplexität), Electron (~150 MB, zwei Toolchains). Vom Nutzer per Rückfrage entschieden: pywebview.

## 3. Backend (core)

### 3.1 Portierung 1:1 (nur Import-Pfade/Konstanten angepasst)
- `mvr_reader.py` (231 LOC): `read_mvr(path) → MvrScene` mit defusedxml, ZIP-Bomben-Schutz (1000 Dateien, 100 MB/Datei, 500 MB gesamt, 500 MB XML). **Ergänzung:** Path-Traversal-Filter auf ZIP-Einträge (`..`/absolute Pfade verwerfen).
- `gdtf.py`: `parse_gdtf`, `import_gdtf`, `load_gdtf_library`, `score_match` (Schwellen unverändert), `find_all_gdtf_suggestions` (Kandidaten+Scores, parametrisiert: `top_n`, `threshold=0.3`), Caches inkl. `invalidate_gdtf_cache`. **Ergänzung:** Bibliotheks-Scan indiziert auch `.gdtf`-Dateien ohne JSON-Cache (einmaliges `parse_gdtf` + Cache-Write beim Ordner-Scan), damit ein beliebiger GDTF-Ordner direkt nutzbar ist.
- `share.py`: `GdtfShareClient` (Login `login.php` als Form-POST, Liste `getList.php` mit lokalem Cache + `timestamp`, Suche clientseitig via `token_match`, Download `downloadFile.php?rid=` mit 200-MB-Limit, 401-Relogin, certifi für Frozen-Builds). Session-Cookie via `http.cookiejar` (wie Vorlage). Passwort-Persistenz nur verschlüsselt (DPAPI, `winsec.py`); opt-in „angemeldet bleiben".
- `_coerce.py`, relevante Teile aus `constants.py`, `_validate_safe_path`/`_sanitize_name`/`_atomic_json_write` aus `config.py`.

**Nicht portiert:** `export.py` (VW-JSON-Export), `templates.py`, `format_safe.py`, `models.py` bis auf Muster; Tkinter-UI-Module dienen nur als Verhaltensreferenz.

### 3.2 Neu: `analysis.py`
Schließt die Lücke „MVR-only-Workflow" (alter Enricher brauchte VW-Fixture-Liste):
- `aggregate_fixture_types(scene) → list[FixtureType]` — gruppiert `MvrScene.fixtures` nach normalisiertem Namen (Fallback `gdtf_spec`), zählt Instanzen, sammelt Positionen, vorhandene `gdtf_spec`/`gdtf_mode` als Match-Signal.
- Positions-Auflösung: `AUXData`-Position-Definitionen (UUID→Name) parsen; Fallback Layer-/GroupObject-Namen. Meta-Zeile „24× · Traverse 1–3" entsteht daraus.
- `compute_stats(scene) → MvrStats` — Fixtures, Fixture-Typen, 3D-Meshes (eingebettete Geometrie-Dateien: `.glb`/`.3ds`/…), Positionen.
- `detect_address_collisions(scene, assignments) → list[CollisionWarning]` — Footprint aus gewähltem `GdtfMode.channel_count`, absolute Adressen → `divmod(addr-1, 512)`, Überlappungsintervalle je Universum (Logik aus `ui/views/dmx.py:762` ins Backend gezogen).

### 3.3 Refactored: `enricher.py`
- Signatur neu: `enrich_mvr(scene, assignments: dict[str, Assignment], gdtf_library_dir, gdtf_library, group_by_position) → EnrichResult`. `Assignment = (gdtf_name | None, mode_name | None, removed: bool)`; wirkt pro **Typ**, `_match_fixtures` entfällt.
- Beibehaltene Kernlogik: `_STRIP_TAGS = {CustomCommands, Position}` (Giftelemente), `_clean_gdtf_name` (%40→@), `_update_fixture_element`, `_reorganize_layers` (Layer „MVR Enhancer Export", GroupObject je Position, „3D"-Gruppe), reproduzierbare UUIDs via `uuid5(NAMESPACE_DNS, seed)`.
- **Neu — verwaiste GDTFs entfernen:** Referenz-Set aller `GDTFSpec` im finalen XML bilden; nur referenzierte `.gdtf` in den ZIP schreiben. Meshes werden weiterhin vollständig übernommen („3D-Szene bleibt unangetastet").
- **Neu — strukturierter `EnrichReport`** statt Log-Zeilen: gematchte/entfernte Fixture-Zahlen, eingebettete GDTFs, übernommene Meshes, Positionsgruppen, Liste der Modus-Fallbacks (Typ + gewählter Modus), gestrippte Elemente, verworfene verwaiste GDTFs. Fallback-Kette wie gehabt (Override → Substring-Match → `modes[0]`), aber jeder stille Fallback wird als Warnung gemeldet.
- Semantik „`removed=True`" (bewusst kein Match, z. B. Plugbox) beibehalten: Fixtures des Typs werden aus dem Export entfernt und im Report gelistet.

### 3.4 Datenmodelle (`models.py`, an UI-Bedarf ausgerichtet)
`FixtureType` (name, count, positions, meta_line, existing_spec/mode), `Candidate` (gdtf_name, manufacturer, revision, score, modes[], source: library|share), `Assignment`, `MvrStats`, `ModeFallbackWarning`, `CollisionWarning`, `CleanupSummary`, `EnrichResult` (bytes + report). Alles JSON-serialisierbar (für die JS-Bridge).

## 4. API-Bridge (`api.py`)

pywebview `js_api`; jede Methode gibt JSON-serialisierbare Dicts `{ok, data|error}` zurück. Lang laufende Operationen (MVR laden, Bibliotheks-Scan, Share-Liste, Export) laufen in einem Worker-Thread; Ergebnis-Push an die UI via `window.evaluate_js('app.on(...)')`, damit das Fenster nicht blockiert.

Methoden (v1 komplett):
- Datei: `choose_mvr()` (nativer Dialog), `load_mvr(path)` → `{stats, file_meta, types[] mit candidates[]}`; `remove_mvr()`; `get_recent()` / persistiert automatisch.
- Matching: `set_gdtf(type, gdtf_name)`, `set_mode(type, mode)`, `set_removed(type, bool)`, `set_grouping(bool)` — Server hält den Zustand (Single Source of Truth in Python; UI rendert, was `get_state()` liefert).
- Bibliothek: `choose_library_dir()`, `scan_library()` → Anzahl Dateien; Pfad persistiert.
- Share: `share_login(user, password, remember)`, `share_logout()`, `share_status()`, `share_search(query)` → Trefferliste (rid, fixture, manufacturer, revision, modes, rating), `share_download(rid)` → importiert in Bibliothek, aktualisiert Kandidaten des betroffenen Typs.
- Export: `prepare_export()` → `{stats, warnings[], cleanup_preview, default_path}`; `run_export(path)` → `{path, size, time, report}`; `open_folder(path)`; danach `exportiert`-Zustand.
- Fenster-Titel: „Groh·PA MVR Export — <dateiname>" via `window.set_title` nach Laden/Entfernen.

**Fehlerbild:** Parser-/ZIP-Fehler werden als `{ok:false, error}` gemeldet; UI zeigt sie an der Dropzone in Anlehnung an die Sicherheits-Zeile (Handoff Z. 84). Share-Fehler (401, Netz) erscheinen in der Quellen-Leiste.

## 5. Frontend (`ui/`)

Vanilla HTML/CSS/JS, **pixelgenau nach Handoff-README + Prototyp-Analyse**. Kein Framework; ein `app.js` mit Zustandsobjekt und `render()`-Funktionen je Sektion (Akkordeon-Zustände werden per CSS-Klassen + Inline-Styles umgeschaltet, Transitions wie spezifiziert).

Maßgebliche Feinheiten aus der Prototyp-Analyse (Korrekturen gegenüber README):
- `--blue-600` ist **#1e7cc4** (Token gewinnt gegen README-Text #1B6FB0); `--border-dark` exakt `rgba(255,255,255,0.12)`.
- Akkordeon: Schritt 1 wächst **nicht** (`flex:0 0 auto` aktiv), Schritt 2/3 `1 1 auto`; `max-height` 0↔900px, 520ms `cubic-bezier(0.16,1,0.3,1)`; Zoom `scale(0.96) translateY(-14px)`, Opacity 360ms `ease`; Knoten-Transition 320ms Default-`ease`; Titel-Letterspacing 0.02em, S1 `line-height:1.05`; Rail-Geometrie pro Schritt unterschiedlich (S1 ohne Linie oben, S3 ohne Linie unten).
- Dunkles Select selbst bauen (Prototyp-Bug: weißes Feld): `background:var(--navy-900)`, Border `rgba(255,255,255,0.25)`, `color:#fff`, Chevron hell, `color-scheme:dark`.
- Export-Button: normal Primary-Blau „Exportieren"; bei offenen Warnungen Amber „Mit N Warnungen exportieren" (dynamisch, nicht hartcodiert).
- Badges/Zusammenfassungen („N von M zugeordnet", „N offene Punkte") aus echten Daten berechnen; Problemzeilen-BG nur für offen/Fallback, nicht für „entfernt"; Score `toFixed(2)`, kein Score = En-Dash im Badge, leere Modus-Zelle = Em-Dash.
- Score-Farben: ≥0.90 success · 0.30–0.89 warning · <0.30 danger.
- Schritt-Guards wie im Prototyp: Schritt 2/3 lassen sich per Kopf-Klick immer öffnen; ohne geladenes MVR zeigen sie einen Wartezustand (Text analog zu den Kollabiert-Zusammenfassungen „wartet auf Quell-MVR" / „wartet auf Matching") statt leerer Tabelle/Stats.
- Filter „nur Probleme" als Toggle über der Tabelle (Handoff-Empfehlung, State `nurProbleme`).
- **Offline:** Fonts (Barlow 400–700 + ital, Barlow Condensed 500–700, Barlow Semi Condensed 500/600, JetBrains Mono 400/500) als woff2 gebündelt (OFL); die 16 Lucide-Icons als Inline-SVG (ISC); `hintergrund.jpg` lokal. Keine CDN-Zugriffe.
- Zusätzliche UI gegenüber Prototyp (funktional nötig, im Handoff angelegt): GDTF-Share-Login-Formular (User/Passwort/„angemeldet bleiben") und Share-Suchdialog („Im Share suchen" je Typ) als Modal im Design-System-Stil (dunkle Karte, gleiche Tokens); Bibliothekspfad-Auswahl in der Quellen-Leiste (Klick auf Pfad öffnet Ordnerdialog).

Drag&Drop: pywebview-DOM-Events liefern Pfade über das `pywebviewFullPath`-Attribut der geloggten Files; zusätzlich Klick → nativer Dateidialog (zuverlässig). Beide Wege werden implementiert; scheitert D&D-Pfadauflösung, bleibt der Dialog der Primärweg.

## 6. Persistenz (`settings.py`)

`%APPDATA%/MVR Enhancer/config.json`, atomar geschrieben: `recent_files` (Pfad + Zeitstempel, max 5), `gdtf_library_dir`, `last_export_dir`, `group_by_position`, `share_user`, `share_password_enc` (DPAPI, nur bei „angemeldet bleiben"), Share-Listen-Cache separat (`share_list.json`, mit `timestamp`).

## 7. Tests

pytest; Fixtures programmatisch (keine Binärdateien im Repo):
- Builder-Helpers in `tests/fixtures.py`: minimales gültiges MVR (ZIP + GeneralSceneDescription.xml), MVR mit Giftelementen (`CustomCommands`, `Position`), mit verwaisten GDTFs, mit `%40`-kodierten Namen, mit Adress-Kollision; minimale `.gdtf` (ZIP + description.xml) für pygdtf.
- Übernommene Tests: `test_gdtf_matching.py`, `test_coerce.py`, Pfad-/Namens-Validierung.
- Neue Tests: `read_mvr`-Sicherheitslimits + Traversal, Typ-Aggregation, Positions-Auflösung, Stats, Kollisionserkennung, Enricher-Roundtrip (laden → zuordnen → exportieren → wieder lesen: Giftelemente weg, verwaiste GDTFs weg, UUIDs reproduzierbar, Meshes vollständig), Modus-Fallback-Warnungen, Share-Client gegen gemockte HTTP-Antworten.
- CI führt pytest + ruff vor jedem Build aus.

## 8. Packaging & Release

- **PyInstaller** `--onefile --windowed --name "MVR Enhancer"`; `ui/`-Assets via `datas`; hiddenimports `pygdtf`, `certifi`, `defusedxml`, `clr`-frei (WebView2 via pywebview[edgechromium] → `webview`-Hooks). Smoke-Check nach Build: .exe startet, Fenster erscheint (manuell lokal).
- **CI:** `.github/workflows/release.yml` — auf `windows-latest`: pytest → PyInstaller → bei Tag `v*` GitHub Release mit .exe-Asset. Zusätzlich `ci.yml` (Tests auf Push/PR).
- **Release v0.1.0:** Tag + Release Notes (Features, bekannte Grenzen/Backlog).
- Versions-String im Header: „v0.1.0 · DIN SPEC 15801 · MVR 1.6".

## 9. Risiken & Annahmen

- **WebView2-Runtime** muss auf dem Zielsystem vorhanden sein (Win11: vorinstalliert). Release Notes vermerken das.
- **GDTF-Share-ToS:** API offiziell dokumentiert, normaler Account genügt; Liste wird gecacht (kein Massen-Scraping). Downloads sequenziell.
- **Kein echtes Test-MVR im Repo** — Verifikation gegen echte Vectorworks-Exporte bleibt manuelle Abnahme durch den Nutzer nach v0.1.0.
- **Logo fehlt** (Handoff): Wordmark „GROH·PA" bleibt Platzhalter; App-Icon v1 = generiertes „G"-Icon im Stil des Fenster-Prototyps (Gradient #1e7cc4→#5caedd).
- Demo-Inkonsistenzen des Prototyps („5 von 6" hartcodiert) werden durch berechnete Werte ersetzt — bewusste, dokumentierte Abweichung.
