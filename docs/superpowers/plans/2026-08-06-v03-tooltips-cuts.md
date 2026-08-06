# MVR Enhancer v0.3 Implementation Plan (Tooltips + Cuts)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Platzhalter der gestrichenen Features („Overrides teilen", „Diff zum letzten Export") entfernen und durchgängige erklärende Tooltips ergänzen.

**Architecture:** Reine UI-/Text-Änderungen: statische `title`-Attribute in index.html, dynamische Titles in den app.js-Render-Funktionen, ein Python-Guard-Test pinnt die statischen Attribute und die entfernten Buttons.

**Tech Stack:** Vanilla HTML/JS, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-06-v03-tooltips-cuts-design.md`

## Global Constraints

- Tooltip-Mechanik: ausschließlich native `title`-Attribute — KEIN eigenes Tooltip-Widget, kein neues CSS dafür.
- Alle Tooltip-Texte deutsch, informelles „du", EXAKT wie in den Tabellen dieses Plans (aus der Spec übernommen).
- index.html: Umlaute als HTML-Entities (`&auml;` usw.) wie im Bestand; gerade einfache Quotes in title-Werten.
- app.js: dynamische title-Werte IMMER durch das vorhandene `esc()` schleusen.
- Keine Tooltips auf Warnungszeilen und auf rein beschrifteten Buttons („Exportieren", „Ordner öffnen").
- Bestehende Tooltips bleiben unverändert: Settings-Icon, `#library-path`, Fallback-Label.
- Die App NIE im Vordergrund starten; Smoke-Check nur per `Start-Process -PassThru; Start-Sleep; Stop-Process`.
- Tests: `.venv\Scripts\python.exe -m pytest` im Repo-Root; `.venv\Scripts\ruff.exe check .` sauber.
- Version am Ende: `0.3.0` in pyproject.toml.

---

### Task 1: Cuts — Overrides-Button, Diff-Button, Hinweistext, README

**Files:**
- Modify: `mvr_enhancer/ui/index.html` (Z.159–161 `sources-bar-right`/`btn-overrides`; Z.266 Hinweistext; Z.275 `btn-diff`)
- Modify: `mvr_enhancer/ui/css/app.css` (Regel `.sources-bar-right`, falls nur dort genutzt)
- Modify: `README.md:40` (Backlog-Zeile)
- Test: `tests/test_ui_tooltips.py` (neu — Teil 1: Absenz-Checks)

**Interfaces:**
- Produces: `tests/test_ui_tooltips.py` mit Helper `_INDEX = pathlib.Path(__file__).resolve().parent.parent / "mvr_enhancer" / "ui" / "index.html"`; Task 2 erweitert dieselbe Datei um Präsenz-Checks.

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `tests/test_ui_tooltips.py`:

```python
"""Guard-Tests fuer die statische UI: gestrichene Buttons bleiben draussen,
erklaerende title-Attribute bleiben drin (siehe v0.3-Spec)."""

import pathlib

_INDEX = pathlib.Path(__file__).resolve().parent.parent / "mvr_enhancer" / "ui" / "index.html"


def _html() -> str:
    return _INDEX.read_text(encoding="utf-8")


def test_cut_buttons_are_gone():
    html = _html()
    assert "btn-overrides" not in html, "Overrides teilen ist gestrichen (v0.3-Spec F1)"
    assert "btn-diff" not in html, "Diff zum letzten Export ist gestrichen (v0.3-Spec F1)"
    assert "Diff zum letzten Export" not in html
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `python -m pytest tests/test_ui_tooltips.py -v`
Expected: FAIL (beide Buttons existieren noch)

- [ ] **Step 3: index.html bereinigen**

1. Den kompletten Block entfernen:

```html
                  <div class="sources-bar-right">
                    <button id="btn-overrides" type="button" class="btn btn-outline btn-sm" disabled title="folgt in einem sp&auml;teren Release">Overrides teilen</button>
                  </div>
```

2. Die Zeile `<button id="btn-diff" ...>Diff zum letzten Export</button>` im `#export-panel-post` entfernen.
3. Hinweistext ändern: `<div class="export-panel-hint">Danach: vollst&auml;ndiger Report + Diff zum letzten Export</div>` → `<div class="export-panel-hint">Danach: vollst&auml;ndiger Report</div>`.

- [ ] **Step 4: CSS prüfen und ggf. bereinigen**

Run: `grep -rn "sources-bar-right" mvr_enhancer/` — wenn nur die eine Regel in app.css übrig ist (kein HTML-Vorkommen mehr), die CSS-Regel `.sources-bar-right { ... }` entfernen. Gibt es weitere Nutzer, Regel stehen lassen.

- [ ] **Step 5: README-Backlogzeile anpassen**

`README.md` Z.40 alt:

```
- Backlog (noch nicht enthalten): Score-Legende-Tooltip, Detailansicht der Adress-Kollision, „Overrides teilen", „Diff zum letzten Export".
```

neu:

```
- Backlog (noch nicht enthalten): Detailansicht der Adress-Kollision. („Overrides teilen" und „Diff zum letzten Export" sind bewusst gestrichen.)
```

- [ ] **Step 6: Tests + Lint**

Run: `python -m pytest tests/test_ui_tooltips.py -v; python -m pytest -q; ruff check .`
Expected: alles grün

- [ ] **Step 7: Commit**

```bash
git add mvr_enhancer/ui/index.html mvr_enhancer/ui/css/app.css README.md tests/test_ui_tooltips.py
git commit -m "feat(ui): gestrichene Platzhalter entfernt (Overrides teilen, Diff zum letzten Export)"
```

---

### Task 2: Statische Tooltips (index.html)

**Files:**
- Modify: `mvr_enhancer/ui/index.html`
- Test: `tests/test_ui_tooltips.py` (erweitern)

**Interfaces:**
- Consumes: `tests/test_ui_tooltips.py` mit `_html()`-Helper aus Task 1.

- [ ] **Step 1: Failing Tests schreiben**

An `tests/test_ui_tooltips.py` anhängen:

```python
# Anker → Pflicht-Fragment des title-Attributs. Bewusst Fragmente statt
# Volltexte: Wording-Feinschliff soll den Test nicht brechen, das Vorhandensein
# der Erklaerung schon.
_EXPECTED_TITLES = {
    "chk-gruppieren": "Fasst Fixtures im Export nach ihrer Position",
    "seg-single": "Alles in einem Layer",
    "seg-per-layer": "3D-Objekte bleiben in ihren Original-Layern",
    "filter-problems": "Zeigt nur Typen mit offenen Punkten",
    "score-th": "Score-Legende",
    "export-uuid-row": "grandMA3 erkennt Re-Importe wieder",
    "es-matched": "Fixtures mit konkreter GDTF-Zuordnung",
    "es-embedded": "eingebettet",
    "es-meshes": "3D-Geometrien",
    "es-positions": "Positions-Gruppen im Export",
    "btn-share-login": "GDTF-Share-Datenbank",
}


def test_static_tooltips_present():
    html = _html()
    for anchor, fragment in _EXPECTED_TITLES.items():
        assert fragment in html, f"Tooltip-Fragment fuer {anchor} fehlt: {fragment!r}"
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `python -m pytest tests/test_ui_tooltips.py::test_static_tooltips_present -v`
Expected: FAIL

- [ ] **Step 3: title-Attribute setzen**

In index.html (exakte Texte; Platzierung am genannten Element):

| Element | title-Attribut |
|---|---|
| `<label class="chk">` um `#chk-gruppieren` | `Fasst Fixtures im Export nach ihrer Position (z. B. Traverse 1) zu Gruppen zusammen &mdash; in grandMA3 als Grouping sichtbar.` |
| `#seg-single` | `Alles in einem Layer 'MVR Enhancer Export': Fixtures plus eine 3D-Gruppe mit allen Objekten. Empfohlen f&uuml;r einfache Shows.` |
| `#seg-per-layer` | `Fixtures im Layer 'MVR Enhancer Export'; 3D-Objekte bleiben in ihren Original-Layern (dort je ein 3D-Grouping). Original-Layer ohne 3D-Objekte entfallen.` |
| `<label class="chk">` um `#filter-problems` | `Zeigt nur Typen mit offenen Punkten: ohne Zuordnung, entfernt oder mit Modus-Fallback.` |
| `<th>Score</th>` (Matching-Tabelle) | `Score-Legende: ab 0.90 sicherer Treffer &middot; 0.30 bis 0.89 bitte pr&uuml;fen &middot; unter 0.30 unwahrscheinlich.` |
| `<div class="export-uuid-row">` | `Gleiche Eingaben erzeugen exakt dieselben UUIDs &mdash; grandMA3 erkennt Re-Importe wieder, statt Duplikate anzulegen.` |
| `.stat`-Div um `#es-matched` | `Fixtures mit konkreter GDTF-Zuordnung, die exportiert werden &mdash; gemessen an allen Fixtures im Quell-MVR.` |
| `.stat`-Div um `#es-embedded` | `Anzahl der GDTF-Dateien, die in das exportierte MVR eingebettet werden.` |
| `.stat`-Div um `#es-meshes` | `3D-Geometrien aus dem Quell-MVR, die unver&auml;ndert &uuml;bernommen werden.` |
| `.stat`-Div um `#es-positions` | `Positions-Gruppen im Export (nur bei aktivierter Positions-Gruppierung).` |
| `#btn-share-login` | `Meldet dich an der &ouml;ffentlichen GDTF-Share-Datenbank an, um fehlende GDTFs zu suchen und herunterzuladen.` |

Hinweis: In title-Attributen funktionieren HTML-Entities (`&mdash;`, `&uuml;`) — Browser dekodiert sie im Tooltip. Der Guard-Test prüft nur die entity-freien Fragmente.

- [ ] **Step 4: Tests + Lint**

Run: `python -m pytest tests/test_ui_tooltips.py -v; python -m pytest -q; ruff check .`
Expected: grün

- [ ] **Step 5: Commit**

```bash
git add mvr_enhancer/ui/index.html tests/test_ui_tooltips.py
git commit -m "feat(ui): statische Tooltips fuer Gruppierung, Export-Modi, Score-Legende, Stats"
```

---

### Task 3: Dynamische Tooltips (app.js) + Version 0.3.0

**Files:**
- Modify: `mvr_enhancer/ui/js/app.js` (`scoreCellHtml` ~Z.776, `sourceBadgeHtml` ~Z.861, `gdtfCellHtml` ~Z.785, `renderRecentList` ~Z.723)
- Modify: `pyproject.toml` (version)

**Interfaces:**
- Consumes: bestehendes `esc()` in app.js.

- [ ] **Step 1: scoreCellHtml erweitern**

```js
  function scoreCellHtml(candidate) {
    if (!candidate) {
      return '<span class="badge tone-ondark" title="Kein Score — die Zuordnung stammt nicht aus dem Matching (z. B. Share-Download) oder fehlt.">–</span>';
    }
    var score = candidate.score;
    var tone = score >= 0.9 ? "success" : score >= 0.3 ? "warning" : "danger";
    var scoreTitle = "Score " + score.toFixed(2) + " — ab 0.90 sicher, 0.30 bis 0.89 pruefen, unter 0.30 unwahrscheinlich.";
    return '<span class="badge tone-' + tone + '" title="' + scoreTitle + '">' + score.toFixed(2) + "</span>";
  }
```

- [ ] **Step 2: sourceBadgeHtml erweitern**

```js
  function sourceBadgeHtml(assignment) {
    if (assignment.removed) {
      return '<span class="badge tone-ondark" title="Wird beim Export entfernt (z. B. Plugbox oder Hilfsobjekt ohne GDTF).">entfernt</span>';
    }
    if (!assignment.gdtf_name) {
      return '<span class="badge tone-danger" title="Noch keine GDTF zugeordnet — offene Typen werden beim Export entfernt.">offen</span>';
    }
    if (assignment.source === "share") {
      return '<span class="badge tone-brand" title="Per GDTF-Share-Download zugeordnet.">Share</span>';
    }
    return '<span class="badge tone-ondark" title="Aus deinem lokalen GDTF-Bibliotheksordner zugeordnet.">Bibliothek</span>';
  }
```

- [ ] **Step 3: gdtfCellHtml — voller Dateiname als title am Select**

Die Select-Rückgabe am Funktionsende ändern (nur wenn etwas zugeordnet ist, sonst kein title-Attribut):

```js
    var selectTitle = assignment.gdtf_name ? ' title="' + esc(assignment.gdtf_name) + '"' : "";
    return (
      '<select class="sel-dark sel-gdtf" data-type-key="' + esc(type.key) + '"' + selectTitle + '>' +
      options.join("") + "</select>"
    );
```

Achtung: `sel-gdtf`-Selects werden bei `set_gdtf` neu gerendert — der title aktualisiert sich dadurch automatisch mit; keine weitere Logik nötig.

- [ ] **Step 4: renderRecentList — voller Pfad als title**

In der Zeilen-Template-Funktion das `.recent-row`-Div erweitern:

```js
          '<div class="recent-row" data-path="' + esc(entry.path) + '" title="' + esc(entry.path) + '">' +
```

- [ ] **Step 5: Version bump**

`pyproject.toml`: `version = "0.2.0"` → `version = "0.3.0"`.

- [ ] **Step 6: Smoke-Check + Suite + Lint**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log (`%APPDATA%\MVR Enhancer\mvr-enhancer.log`) ohne JS-/evaluate_js-Fehler. Dann: `python -m pytest -q; ruff check .` → grün.

- [ ] **Step 7: Commit**

```bash
git add mvr_enhancer/ui/js/app.js pyproject.toml
git commit -m "feat(ui): dynamische Tooltips (Score, Quelle, GDTF-Name, Pfade), Version 0.3.0"
```
