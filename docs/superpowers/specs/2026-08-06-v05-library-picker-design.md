# MVR Enhancer v0.5 — Bibliotheks-Picker statt Riesen-Dropdown (Design)

Datum: 2026-08-06 · Status: vom Nutzer vorgegeben (Chat; Pläne/Specs auto-akzeptiert) · Basis: main nach v0.4.0 (5a9f269)

## Problem (Nutzer-Report mit Screenshot)

Das v0.4-GDTF-Dropdown zeigt die gesamte Bibliothek (43+ Einträge) inline —
unhandlich. Nutzer-Vorgabe wörtlich: Dropdown reduziert auf „nicht
zugeordnet" / „aktiv entfernt" / Vorschläge; die Bibliothek öffnet sich
über einen eigenen Knopf mit „Buch"-Symbol ZWISCHEN Dropdown und
Share-(Globus-)Symbol.

## Ziel

1. **F1 — Dropdown verschlanken:** Sonder-Einträge + Synthetic-Sicherheitsnetz
   + optgroup „Vorschläge". Die optgroup „Gesamte Bibliothek" entfällt.
2. **F2 — Buch-Button:** Neuer Icon-Button (Lucide `book-open`) an jeder
   Zeile zwischen GDTF-Select und Globus-Button; öffnet den
   Bibliotheks-Picker für diesen Typ. Tooltip „Aus der Bibliothek w&auml;hlen".
3. **F3 — Bibliotheks-Picker-Modal:** Durchsuchbare Liste aller
   Bibliotheks-GDTFs; Klick ordnet zu.
4. Release **v0.5.0**.

## Nicht-Ziele

- Keine Backend-Änderung (`library.files` und `set_gdtf` aus v0.4 reichen).
- Keine Mehrfachauswahl, keine Vorschau von GDTF-Details im Picker.

## F1 — Dropdown (app.js `gdtfCellHtml`)

- `libraryOptions`-Aufbau und die optgroup „Gesamte Bibliothek" entfernen;
  `libraryFiles` wird in `gdtfCellHtml` nur noch für `assignedKnown`
  gebraucht (Synthetic-Netz: eine Bibliothek-Zuordnung außerhalb der
  Kandidaten muss WEITER als selektierte Option erscheinen — sie wird jetzt
  regulär über die Synthetic-Option abgedeckt, da sie nicht mehr in einer
  Bibliotheks-optgroup steht). Konsequenz: `assignedKnown` prüft nur noch
  `candidateNames` — eine Nicht-Kandidaten-Zuordnung (aus dem Picker)
  bekommt die Synthetic-Option mit `selected`. Der Sentinel/„nicht
  zugeordnet"-Mechanismus bleibt unverändert (v0.4).

## F2 — Buch-Button

- `icons.js`: neues Icon `book-open` (Lucide, gleiche SVG-Konventionen wie
  die vorhandenen Einträge: 24er viewBox, stroke currentColor, width 2):
  `<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>`
- `gdtfCellHtml`: zwischen Select und Globus-Button:
  `<button type="button" class="btn-share-ico btn-lib-browse" data-type-key data-type-name title="Aus der Bibliothek w&auml;hlen">` mit
  `iconSpanHtml("book-open", "ic-15 ic-blue300")`. (Wiederverwendet die
  `.btn-share-ico`-Optik; keine neue CSS-Klasse nötig außer dem
  Delegations-Hook `btn-lib-browse`.)
- tbody-Click-Delegation: `.btn-lib-browse` → `openLibModal(typeKey, typeName)`.

## F3 — Bibliotheks-Picker-Modal

Markup (index.html, nach dem Share-Such-Modal, gleiche Bausteine
`modal-overlay`/`modal-card`/`modal-close`/`modal-search-input`):

- `#modal-lib-browse` · Titel „GDTF aus der Bibliothek w&auml;hlen" ·
  Untertitel `#lib-browse-type` (Typ-Name, per textContent gesetzt) ·
  Filter-Input `#lib-browse-input` (Placeholder „Bibliothek filtern&hellip;") ·
  Liste `#lib-browse-results` (Stil der `share-results`-Liste).

Verhalten (app.js):

- Zustand `libModal = { typeKey: null, typeName: "", filter: "" }`.
- `openLibModal(typeKey, typeName)`: Zustand setzen, Filter leeren,
  `renderLibModal()`, `openModal("modal-lib-browse")`, Fokus auf den
  Filter-Input.
- `renderLibModal()`: filtert `serverState.library.files` case-insensitiv
  per Substring (`name.toLowerCase().indexOf(filter) !== -1`), rendert
  Zeilen (`esc(name)`, `data-name`); die aktuell zugeordnete GDTF des Typs
  (falls vorhanden und nicht removed) bekommt eine „aktiv"-Markierung
  (Check-Icon oder Klasse). Leere Bibliothek → Hinweiszeile „Keine GDTFs in
  der Bibliothek — Ordner w&auml;hlen oder im Share suchen."; leerer Filter-
  Treffer → „Kein Treffer f&uuml;r deinen Filter.".
- Input-Event auf `#lib-browse-input` → `libModal.filter` + `renderLibModal()`.
- Klick-Delegation auf `#lib-browse-results`: Zeile mit `data-name` →
  `callApi("set_gdtf", libModal.typeKey, name)`, dann
  `closeModal("modal-lib-browse")`. (`set_gdtf` liefert den frischen State
  synchron zurück — Tabelle rendert wie bei jeder Zuordnung.)
- Modal-Schließen (X, Overlay, Esc) über die bestehende Modal-Mechanik;
  beim Schließen keinen Zustand persistieren (nächstes Öffnen startet
  frisch).

## Tests

- Guard-Test-Erweiterung (`tests/test_ui_tooltips.py` oder neue Datei
  `tests/test_ui_lib_browse.py`): index.html enthält `modal-lib-browse`,
  `lib-browse-input`, `lib-browse-results`; icons.js enthält `book-open`;
  app.js enthält KEINE optgroup „Gesamte Bibliothek" mehr (Regression des
  Nutzer-Wunschs).
- JS-Verhalten: Task-Review + Smoke-Check.
- Version 0.5.0 an allen VIER Stellen + 2 Test-Assertions (Checkliste!).

## Risiken

- Gering; größte Fläche ist das neue Modal — es klont bewusst die
  Share-Such-Mechanik (Zustand + render + Delegation), die sich bewährt hat.
