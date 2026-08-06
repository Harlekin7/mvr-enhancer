# MVR Enhancer v0.5 Implementation Plan (Bibliotheks-Picker)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das GDTF-Dropdown zeigt nur noch Sonder-Einträge + Vorschläge; die gesamte Bibliothek öffnet sich über einen Buch-Button in einem durchsuchbaren Picker-Modal.

**Architecture:** Reines Frontend: Dropdown verschlankt, neuer Icon-Button je Zeile, neues Modal nach dem Muster des Share-Such-Modals (Zustand + render + Delegation). Backend unverändert (`library.files`, `set_gdtf` aus v0.4).

**Tech Stack:** Vanilla HTML/JS/CSS, pytest (Guard-Tests), ruff.

**Spec:** `docs/superpowers/specs/2026-08-06-v05-library-picker-design.md`

## Global Constraints

- Dropdown-Inhalt exakt: `— nicht zugeordnet —` (value "") · `— aktiv entfernt —` (value `__removed__`) · Synthetic-Option (selected, wenn Zuordnung kein Kandidat ist — deckt jetzt AUCH Bibliothek-Zuordnungen aus dem Picker ab) · optgroup `Vorschl&auml;ge`. KEINE optgroup „Gesamte Bibliothek" mehr.
- Buch-Button: Lucide `book-open` in icons.js (SVG-Konventionen der Datei), Button-Klassen `btn-share-ico btn-lib-browse` (nutzt bestehende Optik), `data-type-key`/`data-type-name`, `title="Aus der Bibliothek w&auml;hlen"`, Position ZWISCHEN Select und Globus-Button.
- Picker-Modal `#modal-lib-browse` mit `#lib-browse-type`, `#lib-browse-input`, `#lib-browse-results`; Filter case-insensitiv Substring; Zeilen-Klick → `set_gdtf` + Modal zu; aktuell zugeordnete GDTF markiert; leere Zustände mit den Spec-Texten.
- Alle dynamischen Werte via `esc()`; Typ-Name per `textContent` (nie innerHTML).
- Deutsche UI, du-Form; App NIE im Vordergrund starten (Smoke-Check-Muster).
- Tests: `.venv\Scripts\python.exe -m pytest`, `.venv\Scripts\ruff.exe check .` sauber.
- Version am Ende `0.5.0` an ALLEN VIER Stellen (pyproject.toml, `mvr_enhancer/__init__.py`, index.html-Header, README-Überschrift „Bekannte Grenzen") + 2 Test-Assertions (test_api.py, test_smoke.py).

---

### Task 1: Picker-Modal + Buch-Button + Dropdown verschlanken

**Files:**
- Modify: `mvr_enhancer/ui/assets/icons.js` (Icon `book-open`)
- Modify: `mvr_enhancer/ui/index.html` (Modal nach `#modal-share-search`)
- Modify: `mvr_enhancer/ui/js/app.js` (`gdtfCellHtml`, tbody-Click-Delegation, `libModal`-Zustand, `openLibModal`/`renderLibModal`, Input-/Klick-Delegation des Modals)
- Modify: `mvr_enhancer/ui/css/app.css` (nur falls die `share-results`-Zeilenklassen nicht 1:1 wiederverwendbar sind — Klassen ansehen und möglichst wiederverwenden)
- Test: `tests/test_ui_lib_browse.py` (neu)

**Interfaces:**
- Consumes: `serverState.library.files` (v0.4), `callApi("set_gdtf", key, name)`, `openModal`/`closeModal`, `esc()`, `iconSpanHtml()`.
- Produces: `openLibModal(typeKey, typeName)`, `renderLibModal()`, Markup-Ids `modal-lib-browse`/`lib-browse-type`/`lib-browse-input`/`lib-browse-results`.

- [ ] **Step 1: Failing Guard-Test schreiben**

Neue Datei `tests/test_ui_lib_browse.py`:

```python
"""Guard-Tests fuer den Bibliotheks-Picker (v0.5): Modal-Markup existiert,
das Buch-Icon ist registriert, und die Bibliothek haengt nicht mehr als
optgroup im GDTF-Dropdown (Nutzer-Vorgabe v0.5)."""

import pathlib

_UI = pathlib.Path(__file__).resolve().parent.parent / "mvr_enhancer" / "ui"


def test_lib_browse_modal_markup_present():
    html = (_UI / "index.html").read_text(encoding="utf-8")
    for anchor in ("modal-lib-browse", "lib-browse-type", "lib-browse-input", "lib-browse-results"):
        assert anchor in html, f"Picker-Anker fehlt: {anchor}"
    assert "Aus der Bibliothek" in html.replace("&auml;", "ä") or "Aus der Bibliothek" in html


def test_book_icon_registered():
    icons = (_UI / "assets" / "icons.js").read_text(encoding="utf-8")
    assert "book-open" in icons


def test_full_library_optgroup_removed_from_dropdown():
    app_js = (_UI / "js" / "app.js").read_text(encoding="utf-8")
    assert "Gesamte Bibliothek" not in app_js
    assert "btn-lib-browse" in app_js
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `python -m pytest tests/test_ui_lib_browse.py -v`
Expected: FAIL (Anker existieren noch nicht / optgroup existiert noch)

- [ ] **Step 3: icons.js — book-open ergänzen**

In `mvr_enhancer/ui/assets/icons.js` im `window.ICONS`-Objekt (alphabetisch passend einsortieren, gleiche Escaping-Konventionen wie die Nachbarn):

```
  "book-open": "<svg class=\"lucide lucide-book-open\" xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"> <path d=\"M12 7v14\" /> <path d=\"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z\" /> </svg>",
```

- [ ] **Step 4: index.html — Picker-Modal**

Direkt NACH dem schließenden `</div>` des `#modal-share-search`-Blocks:

```html
<!-- ══ Modal: GDTF aus Bibliothek wählen ══ -->
<div id="modal-lib-browse" class="modal-overlay hidden">
  <div class="modal-card">
    <button type="button" class="modal-close" data-modal-close="modal-lib-browse">
      <span class="icon ic-20 ic-muted" data-icon="x"></span>
    </button>
    <h3 class="modal-title">GDTF aus der Bibliothek w&auml;hlen</h3>
    <div id="lib-browse-type" class="modal-subtitle"></div>
    <div class="modal-field">
      <input id="lib-browse-input" type="text" class="modal-search-input" placeholder="Bibliothek filtern&hellip;" />
    </div>
    <div id="lib-browse-results" class="share-results"></div>
  </div>
</div>
```

Vorher prüfen: Nutzt das Share-Such-Modal eine Subtitle-Klasse (`modal-subtitle` oder ähnlich)? Existiert keine, eine minimale Regel in app.css ergänzen (`.modal-subtitle { margin: -6px 0 12px; font-size: 13px; color: var(--text-inverse-muted); }`) — ansonsten die vorhandene Klasse verwenden. Die Card-Größenklasse (`modal-card` vs. `modal-card-sm`) am Share-Such-Modal ablesen und übernehmen.

- [ ] **Step 5: app.js — Dropdown verschlanken**

In `gdtfCellHtml`:

1. Den kompletten `libraryOptions`-Block (Aufbau + `options.push('<optgroup label="Gesamte Bibliothek">…')`) entfernen.
2. `assignedKnown` reduzieren auf: `var assignedKnown = selectedName && candidateNames[selectedName];` — damit rendert eine Picker-Zuordnung (kein Kandidat) die Synthetic-Option mit `selected` (Sicherheitsnetz-Kommentar entsprechend anpassen: er deckt jetzt regulär Bibliothek-Zuordnungen ab, nicht nur Share-Sonderfälle).
3. Zwischen Select und Globus-Button den Buch-Button einfügen:

```js
      '<button type="button" class="btn-share-ico btn-lib-browse" data-type-key="' + esc(type.key) +
      '" data-type-name="' + esc(type.name) + '" title="Aus der Bibliothek w&auml;hlen">' +
      iconSpanHtml("book-open", "ic-15 ic-blue300") +
      "</button>" +
```

- [ ] **Step 6: app.js — Picker-Logik**

Zustand bei den anderen Modal-Zuständen:

```js
  var libModal = { typeKey: null, typeName: "", filter: "" };
```

Funktionen (neben `openSearchModal`/`renderSearchModal` platzieren):

```js
  function openLibModal(typeKey, typeName) {
    libModal.typeKey = typeKey;
    libModal.typeName = typeName;
    libModal.filter = "";
    $("lib-browse-input").value = "";
    $("lib-browse-type").textContent = typeName;
    renderLibModal();
    openModal("modal-lib-browse");
    $("lib-browse-input").focus();
  }

  function renderLibModal() {
    var el = $("lib-browse-results");
    var files = (serverState && serverState.library && serverState.library.files) || [];
    if (!files.length) {
      el.innerHTML = '<div class="muted-text">Keine GDTFs in der Bibliothek &mdash; Ordner w&auml;hlen oder im Share suchen.</div>';
      return;
    }
    var filter = libModal.filter.toLowerCase();
    var type = (serverState.types || []).find(function (t) { return t.key === libModal.typeKey; });
    var current = type && type.assignment && !type.assignment.removed ? type.assignment.gdtf_name : "";
    var rows = files
      .filter(function (name) { return !filter || name.toLowerCase().indexOf(filter) !== -1; })
      .map(function (name) {
        var isCurrent = name === current;
        return (
          '<div class="recent-row lib-row" data-name="' + esc(name) + '">' +
          iconSpanHtml("file-box", "ic-16 ic-blue300") +
          '<span class="recent-name">' + esc(name) + "</span>" +
          (isCurrent ? '<span class="badge tone-ondark">aktuell</span>' : "") +
          "</div>"
        );
      });
    el.innerHTML = rows.length
      ? rows.join("")
      : '<div class="muted-text">Kein Treffer f&uuml;r deinen Filter.</div>';
  }
```

(`recent-row`/`recent-name` sind vorhandene Zeilen-Styles aus der Zuletzt-Liste — wiederverwenden; wenn deren Hover im Modal nicht greift, `.lib-row`-Hover mit demselben `rgba(92,174,221,0.10)` in app.css ergänzen.)

Delegation/Bindings (bei den anderen Modal-Bindings):

```js
    $("lib-browse-input").addEventListener("input", function (e) {
      libModal.filter = e.target.value || "";
      renderLibModal();
    });
    $("lib-browse-results").addEventListener("click", function (e) {
      var row = e.target.closest(".lib-row");
      if (!row || !libModal.typeKey) return;
      callApi("set_gdtf", libModal.typeKey, row.dataset.name);
      closeModal("modal-lib-browse");
    });
```

tbody-Click-Delegation um den Buch-Button erweitern (VOR dem `.btn-share-search`-Zweig oder danach — beide sind disjunkt):

```js
      var libBtn = e.target.closest(".btn-lib-browse");
      if (libBtn) {
        openLibModal(libBtn.dataset.typeKey, libBtn.dataset.typeName);
        return;
      }
```

Prüfen: Behandelt die bestehende Modal-Mechanik (Esc/Overlay/X) alle Modals generisch über `data-modal-close`/`modal-overlay`-Klassen? Wenn ja, ist nichts weiter nötig; wenn das Share-Such-Modal einen Sonderfall in `closeModal` hat (app.js ~Z.478), prüfen, ob der Picker einen analogen Reset braucht (nicht nötig — `openLibModal` setzt alles frisch).

- [ ] **Step 7: Guard-Tests grün + Suite + Lint + Smoke**

Run: `python -m pytest tests/test_ui_lib_browse.py -v; python -m pytest -q; ruff check .`
Expected: grün. Dann Smoke:

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log ohne JS-/evaluate_js-Fehler.

- [ ] **Step 8: Commit**

```bash
git add mvr_enhancer/ui/assets/icons.js mvr_enhancer/ui/index.html mvr_enhancer/ui/js/app.js mvr_enhancer/ui/css/app.css tests/test_ui_lib_browse.py
git commit -m "feat(ui): Bibliotheks-Picker hinter Buch-Button, Dropdown auf Vorschlaege verschlankt"
```

---

### Task 2: Version 0.5.0 + README

**Files:**
- Modify: `pyproject.toml`, `mvr_enhancer/__init__.py`, `mvr_enhancer/ui/index.html` (Header), `README.md`, `tests/test_api.py`, `tests/test_smoke.py`

- [ ] **Step 1: Version an allen Stellen**

`0.4.0` → `0.5.0` in: pyproject.toml, `__init__.py` (`__version__`), index.html-Header-String, README-Überschrift „Bekannte Grenzen (v0.4.0)", die 2 Test-Assertions. Per grep nach `0.4.0` verifizieren, dass außerhalb docs/ nichts übrig bleibt.

- [ ] **Step 2: README anpassen**

Die v0.4-Formulierung „wählst du im GDTF-Dropdown unter ‚Gesamte Bibliothek'…" ersetzen durch die neue Bedienung: „Passt kein Vorschlag, öffnest du mit dem Buch-Button neben dem Dropdown die durchsuchbare Bibliotheks-Liste — oder springst mit dem Globus-Button direkt in die GDTF-Share-Suche." (Ton anpassen erlaubt, Inhalt bindend.)

- [ ] **Step 3: Suite + Lint + Commit**

Run: `python -m pytest -q; ruff check .` → grün

```bash
git add pyproject.toml mvr_enhancer/__init__.py mvr_enhancer/ui/index.html README.md tests/test_api.py tests/test_smoke.py
git commit -m "docs: Bibliotheks-Picker dokumentieren, Version 0.5.0"
```
