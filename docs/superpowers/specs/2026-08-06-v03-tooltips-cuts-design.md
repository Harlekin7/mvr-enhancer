# MVR Enhancer v0.3 — Tooltips + Feature-Cuts (Design)

Datum: 2026-08-06 · Status: vom Nutzer freigegeben (Chat; Pläne/Specs auto-akzeptiert) · Basis: main nach v0.2.0 (95bbcde)

## Ziel

1. **F1 — Cuts:** Die Platzhalter der gestrichenen Features verschwinden aus der
   UI: „Overrides teilen"-Button (Quellen-Leiste, Schritt 2) und „Diff zum
   letzten Export"-Button (Export-Panel, Schritt 3) samt Hinweistext-Anpassung.
   Nutzer-Entscheidung: beide Features werden nie gebaut.
2. **F2 — Durchgängige Tooltips:** Überall dort, wo die App eine Entscheidung
   getroffen hat oder ein Fachbegriff steht, erklärt ein Tooltip das Verhalten.
3. Am Ende: Release **v0.3.0**.

## Nicht-Ziele

- Kein eigenes Tooltip-Widget/CSS: native `title`-Attribute (im Projekt
  etabliert: Settings-Icon, Bibliothekspfad, Fallback-Label; WebView2 rendert
  sie zuverlässig).
- Keine Tooltips auf Warnungszeilen (deren Text IST bereits die Erklärung)
  und keine auf rein beschrifteten Buttons („Exportieren", „Ordner öffnen").
- Multi-DMX-Break-Fix bleibt eigenes, späteres Thema.

## F1 — Cuts

- `index.html`: `<div class="sources-bar-right">` samt `#btn-overrides`
  entfernen (der Wrapper hat keinen weiteren Inhalt; prüfen, ob CSS
  `.sources-bar-right` noch anderweitig greift — wenn nicht, CSS-Regel mit
  entfernen).
- `index.html`: `#btn-diff` entfernen (hat keine JS-Referenzen);
  Hinweistext `#export-panel-pre .export-panel-hint`:
  „Danach: vollst&auml;ndiger Report + Diff zum letzten Export" →
  „Danach: vollst&auml;ndiger Report".
- `README.md` Z.40 (Backlog-Zeile): „Overrides teilen" und „Diff zum letzten
  Export" streichen (Features gecuttet, nicht verschoben); „Score-Legende-
  Tooltip" streichen (wird in diesem Release umgesetzt); übrig bleibt die
  Detailansicht der Adress-Kollision.

## F2 — Tooltips

Alle Texte deutsch, informelles „du". Native `title`-Attribute; dynamische
Titles in app.js immer durch das vorhandene `esc()` schleusen.

### Statisch (index.html)

| Element | title |
|---|---|
| `label.chk` um `#chk-gruppieren` | `Fasst Fixtures im Export nach ihrer Position (z. B. Traverse 1) zu Gruppen zusammen — in grandMA3 als Grouping sichtbar.` |
| `#seg-single` | `Alles in einem Layer "MVR Enhancer Export": Fixtures plus eine 3D-Gruppe mit allen Objekten. Empfohlen für einfache Shows.` |
| `#seg-per-layer` | `Fixtures im Layer "MVR Enhancer Export"; 3D-Objekte bleiben in ihren Original-Layern (dort je ein 3D-Grouping). Original-Layer ohne 3D-Objekte entfallen.` |
| `label.chk` um `#filter-problems` | `Zeigt nur Typen mit offenen Punkten: ohne Zuordnung, entfernt oder mit Modus-Fallback.` |
| `th` „Score" (Spaltenkopf Matching-Tabelle) | `Score-Legende: ab 0.90 sicherer Treffer · 0.30 bis 0.89 bitte prüfen · unter 0.30 unwahrscheinlich.` |
| `.export-uuid-row` | `Gleiche Eingaben erzeugen exakt dieselben UUIDs — grandMA3 erkennt Re-Importe wieder, statt Duplikate anzulegen.` |
| Stat `#es-matched` (`.stat`-Container) | `Fixtures mit konkreter GDTF-Zuordnung, die exportiert werden — gemessen an allen Fixtures im Quell-MVR.` |
| Stat `#es-embedded` | `Anzahl der GDTF-Dateien, die in das exportierte MVR eingebettet werden.` |
| Stat `#es-meshes` | `3D-Geometrien aus dem Quell-MVR, die unverändert übernommen werden.` |
| Stat `#es-positions` | `Positions-Gruppen im Export (nur bei aktivierter Positions-Gruppierung).` |
| `#btn-share-login` | `Meldet dich an der öffentlichen GDTF-Share-Datenbank an, um fehlende GDTFs zu suchen und herunterzuladen.` |

Umlaute in index.html wie im Bestand als HTML-Entities (`&auml;` etc.),
Anführungszeichen in title-Attributen als einfache gerade Quotes.

### Dynamisch (app.js)

| Render-Stelle | title |
|---|---|
| `scoreCellHtml` — Score-Badge | `Score <X.XX> — ab 0.90 sicher, 0.30 bis 0.89 pruefen, unter 0.30 unwahrscheinlich.` (Wert mit `toFixed(2)`); für den „–"-Fall (kein Kandidat): `Kein Score — die Zuordnung stammt nicht aus dem Matching (z. B. Share-Download) oder fehlt.` |
| `sourceBadgeHtml` — „Bibliothek" | `Aus deinem lokalen GDTF-Bibliotheksordner zugeordnet.` |
| `sourceBadgeHtml` — „Share" | `Per GDTF-Share-Download zugeordnet.` |
| `sourceBadgeHtml` — „offen" | `Noch keine GDTF zugeordnet — offene Typen werden beim Export entfernt.` |
| `sourceBadgeHtml` — „entfernt" | `Wird beim Export entfernt (z. B. Plugbox oder Hilfsobjekt ohne GDTF).` |
| `gdtfCellHtml` — `select.sel-gdtf` | Voller aktuell zugeordneter GDTF-Dateiname (`assignment.gdtf_name`, via esc()) — lange Namen werden im Select abgeschnitten, der Tooltip zeigt sie ganz. Kein title, wenn nichts zugeordnet. |
| `renderRecentList` — `.recent-row` | Voller Dateipfad (`entry.path`, via esc()). |

Bestand bleibt: Fallback-Label-Tooltip (`Fallback: erster Modus der GDTF`),
Settings-Icon, Bibliothekspfad.

## Tests

- Neuer Guard-Test `tests/test_ui_tooltips.py`: liest `mvr_enhancer/ui/index.html`
  und asserted (a) die statischen title-Attribute der Tabelle oben anhand
  eindeutiger Anker (Element-Id bzw. Score-`th`), (b) dass `btn-overrides`
  und `btn-diff` NICHT mehr vorkommen. Kein HTML-Parser nötig — String-Checks
  reichen (die Datei ist Teil des Repos, kein Nutzer-Input).
- Dynamische Titles (app.js) sind JS — kein Testharness; Absicherung über
  Task-Review + Smoke-Check (App-Start ohne JS-Fehler im Log).

## Risiken

- Keine nennenswerten: reine UI-/Text-Änderungen, kein Backend-Touch.
- `title` auf `<select>` verhält sich in WebView2/Chromium normal (zeigt beim
  Hover über dem geschlossenen Select).
