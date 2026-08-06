# MVR Enhancer v0.4 — Freie GDTF-Zuordnung + Share-Suche pro Zeile (Design)

Datum: 2026-08-06 · Status: vom Nutzer freigegeben (Chat; Pläne/Specs auto-akzeptiert) · Basis: main nach v0.3.0 (e7a7757)

## Problem (Nutzer-Report)

„Wenn von der auto-gematchten Liste keins das richtige ist, hat man keine
Möglichkeit, in den Share zu gehen oder ein völlig anderes zuzuordnen."

Bestandsaufnahme bestätigt zwei Lücken:

1. Der „Im Share suchen"-Button existiert nur im Leerzustand
   (`!type.candidates.length && !assignment.gdtf_name`); sobald Kandidaten
   existieren, gibt es keinen Weg ins Share-Suchmodal.
2. Das GDTF-Select bietet nur die Score-Kandidaten (top_n=5, threshold 0.3)
   an — eine GDTF außerhalb dieser Liste ist nicht wählbar, obwohl das
   Backend (`Api.set_gdtf` → `_modes_from_library`) beliebige
   Bibliotheksnamen bereits akzeptiert.
3. Latenter Folgefehler: Ist eine Nicht-Kandidaten-GDTF zugeordnet (heute
   nur via Share-Download erreichbar, dessen Download nicht zwingend in den
   Kandidaten landet), zeigt `modeCellHtml` nur den einen initialen Modus
   (`channel_count: 0`) — der Nutzer kann den Modus nicht wechseln.

## Problem 2 (Nutzer-Report, nachgereicht)

„Der Ladebalken ist extrem fern ab von der Realität, es dauert meist 10–20
Sekunden … Sowohl MVR laden als auch GDTFs downloaden scheint langsam,
meistens kommt das ‚konnte nicht geladen werden'-Popup und kurz danach ist
es dann doch geladen."

Analyse:

- Der Balken animiert zeitbasiert in 1 s auf 90 % und steht dann — bei
  realen 10–20 s Ladezeit wirkt er kaputt. Der langsame Teil ist das
  Entpacken der eingebetteten Dateien in `_read_mvr_archive` (pro Eintrag
  `zf.read`) plus das Score-Matching.
- Das Popup ist der 30-s-UI-Watchdog: Er misst Gesamtdauer statt Stille.
  Die JS-Seite re-armiert den Watchdog zwar bereits bei jedem
  progress-Event (`onEvent`-progress-Case ruft `armWatchdog`), aber
  während der eigentlichen Arbeit kommen KEINE Events — bei `load_mvr`
  nur das eine Start-Event, bei `share_download` gar keins. Überschreitet
  die Arbeit 30 s, feuert der Watchdog, obwohl alles läuft; der Erfolg
  trifft danach ein.

## Ziel

1. Jede Matching-Zeile erlaubt (a) die Auswahl JEDER GDTF aus der lokalen
   Bibliothek und (b) den Sprung ins Share-Suchmodal — unabhängig davon, ob
   und wie viele Kandidaten es gibt. Die Modus-Auswahl zeigt immer die volle
   Modusliste der zugeordneten GDTF.
2. Der Ladebalken folgt dem ECHTEN Fortschritt (Entpacken → Matching), und
   der Watchdog feuert nur noch nach 30 s STILLE statt 30 s Gesamtdauer —
   getragen von periodischen Fortschritts-Events aus Reader und Downloader.

Release **v0.4.0**.

## Problem 3 (Nutzer-Report, nachgereicht)

Screenshot Schritt 3: „10 Fixtures entfernt · 2 offene Typen" — dabei SIND
die 2 offenen Typen genau diese 10 Fixtures. Die Zählung ist intern
konsistent (offene Typen werden beim Export entfernt und zählen deshalb in
beiden Angaben), aber für den Nutzer unlesbar: „offen" (vergessen?) und
„bewusst entfernt" sind nicht unterscheidbar, und es gibt in der UI keinen
direkten Weg, einen Typ AKTIV zu entfernen (`set_removed(true)` hat keinen
Auslöser — der `removed`-Zustand ist nur über „Doch zuordnen" verlassbar).

## F4 — Dropdown-Zustände: „nicht zugeordnet" vs. „aktiv entfernt"

Das GDTF-Select jeder Zeile führt ZWEI Sonder-Einträge vor den Gruppen:

1. `— nicht zugeordnet —` (value `""`): Zustand „offen"; beim Export wird
   der Typ entfernt UND als offener Typ in der Bereinigungsliste genannt
   (Bestandsverhalten). Selektiert, wenn `!assignment.gdtf_name &&
   !assignment.removed`.
2. `— aktiv entfernt —` (value `"__removed__"`): Zustand „bewusst
   entfernt"; beim Export entfernt, erscheint NICHT als offener Typ.
   Selektiert, wenn `assignment.removed`.

Verhalten:

- Der bisherige removed-Sonderzustand der Zelle (durchgestrichenes „wird
  entfernt" + „Doch zuordnen"-Button) entfällt — auch entfernte Typen
  zeigen das normale Select (mit `— aktiv entfernt —` selektiert) plus
  Globus-Button. Der `btn-reassign`-Delegationszweig in app.js wird
  entfernt.
- Change-Handler: value `"__removed__"` → `callApi("set_removed", key,
  true)`; value `""` → `callApi("set_gdtf", key, "")` (Bestand; `set_gdtf`
  erzeugt `Assignment()` mit `removed=False` — verlässt den
  Entfernt-Zustand); sonst `set_gdtf(key, value)` (erzeugt ebenfalls
  `removed=False` — Zuordnen verlässt den Entfernt-Zustand, Bestand).
- Der Sentinel-Wert `"__removed__"` ist rein UI-seitig; er erreicht das
  Backend nie (der Handler verzweigt vorher). Kollisionsrisiko mit echten
  GDTF-Namen: praktisch null, dennoch prüft der Handler den Sentinel VOR
  dem set_gdtf-Zweig.
- Score-/Quelle-/Modus-Zellen im removed-Zustand: wie bisher („–", Badge
  „entfernt", „—").
- Tooltips: `— aktiv entfernt —`-Option braucht keinen eigenen title; das
  Quelle-Badge „entfernt" erklärt die Konsequenz bereits (v0.3-Tooltip).
- Die Backend-Zählung (`_compute_cleanup_preview`, `open_count`) bleibt
  unverändert — sie unterscheidet bereits korrekt; mit dem neuen UI-Weg
  kann der Nutzer die 2 „offenen" Typen nun aktiv auf „entfernt" stellen,
  womit die verwirrende Doppelnennung verschwindet.

## F2 — Echter Ladefortschritt + stiller Watchdog

### Reader-Callback

`read_mvr(path, progress=None)` und `_read_mvr_archive(zf, path, progress)`:
`progress` ist ein optionales Callable `(done: int, total: int) -> None`,
aufgerufen einmal vor der Schleife (`0, total`) und nach jedem gelesenen
Archiv-Eintrag (`done, total`; `total` = Anzahl der zu lesenden Einträge).
Kein Callback → Verhalten wie heute. Exceptions aus dem Callback werden im
Reader NICHT gefangen (der Api-Callback fängt selbst; der Reader bleibt
schlank). `run_export`s `read_mvr`-Aufruf bleibt ohne Callback.

### Api: Fortschritts-Events

- `_do_load_mvr` übergibt einen Callback, der gedrosselt (nur wenn der
  Prozentwert um ≥ 3 Punkte gestiegen ist ODER ≥ 500 ms seit dem letzten
  Event vergangen sind; Exceptions intern gefangen + geloggt) Events pusht:
  `{"type": "progress", "method": "load_mvr", "data": {"phase": "read", "percent": P}}`
  mit P = 5 + (done/total) × 70 (also 5–75 %; total==0 → direkt 75).
- Nach dem Lesen, vor Aggregation/Matching:
  `{"phase": "match", "percent": 80}`; nach dem Kandidaten-Aufbau:
  `{"phase": "match", "percent": 95}`. Das bestehende Start-Event
  (`{"phase": "start"}`) bleibt die erste Emission.
- `GdtfShareClient._request(..., progress=None)` reicht einen Callback
  `(downloaded_bytes: int, total_bytes: int) -> None` in die Chunk-Schleife
  (`total_bytes` aus dem `Content-Length`-Header, 0 wenn unbekannt);
  `download(...)` bekommt denselben optionalen Parameter und reicht durch.
  `_do_share_download` emittiert gedrosselt (gleiche Regel)
  `{"type": "progress", "method": "share_download", "data": {"percent": P}}`
  (P aus Bytes, bei unbekanntem total: pulsierende Aktivitäts-Events mit
  `"percent": null` — sie dienen dann nur dem Watchdog).

### UI (app.js)

- `dzStart()` wie bisher (Klasse, Titel „Lade …"), aber die Füllung kriecht
  initial nur auf 15 % in 2 s (statt 90 % in 1 s) — Fallback für sehr
  kleine Dateien, deren Events sofort durchlaufen.
- Neue Funktion `dzProgress(percent)`: setzt die Füllung monoton (kleinere
  Werte werden ignoriert) per `transform: scaleX(percent/100)` mit
  `transition: transform 400ms linear`. Deckel bei 95 % — 100 % gibt es
  nur über `dzFinish`.
- `onEvent`-progress-Case: `load_mvr`-Events mit `data.percent` →
  `dzProgress`; Events mit `phase:"start"` → `dzStart` (Bestand).
  Watchdog-Re-Arm-Regel erweitert: re-armiert wird bei JEDEM progress-Event
  eines Methods, das in `WATCHDOG_ARM_ON_PROGRESS` steht ODER dessen
  Watchdog gerade pendent ist (deckt `share_download` ab, dessen Watchdog
  beim Aufruf armiert wird).
- Suchmodal: Während eines Downloads zeigt der Download-Button des
  betroffenen Ergebnisses den Prozentwert („lädt … 42 %", bei
  `percent: null` unverändert „lädt …") — `searchModal.downloadPercent`
  wird aus den `share_download`-progress-Events gespeist und beim
  Abschluss/Fehler zurückgesetzt.
- Erfolgs-/Fehler-/Min-1-s-Choreografie: unverändert (v0.2-Verhalten).

Damit verschwindet der Fehlalarm konstruktiv: Solange Entpacken oder
Download Fortschritt melden, wird der 30-s-Timer immer wieder neu gestellt;
er feuert nur noch, wenn wirklich 30 s lang nichts passiert.

## Nicht-Ziele

- Kein Freitext-/Datei-Picker für GDTFs außerhalb des Bibliotheksordners.
- Keine Änderung an Score-Matching, Kandidaten-Berechnung oder `set_gdtf`.
- Kein Suchfeld im Select (natives `<select>` reicht; die Bibliothek liegt
  im zwei- bis niedrigen dreistelligen Bereich).

## Backend (api.py)

`get_state()["data"]` wird erweitert (beides unter dem bestehenden Lock):

1. `library.files: list[str]` — ALLE Namen der geladenen Bibliothek
   (`sorted(self._gdtf_library.keys(), key=str.casefold)`).
2. Pro Typ in `types[]` ein neues Feld `assigned_modes: list[dict]` — die
   Modi (`{"name", "channel_count"}`) der aktuell zugeordneten GDTF:
   - Kandidat vorhanden (`_find_candidate`) → dessen `modes`;
   - sonst `_modes_from_library(assignment.gdtf_name)`;
   - keine Zuordnung → `[]`.

`set_gdtf`, `set_mode`, Share-Download: unverändert (können das bereits).

## Frontend (app.js + app.css + icons)

### GDTF-Zelle (`gdtfCellHtml`) — neu strukturiert

- **removed-Zustand:** unverändert („wird entfernt" + „Doch zuordnen").
- **Alle anderen Zustände** (auch der bisherige Leerzustand — der Block
  „kein Treffer in der Bibliothek" + Button entfällt ersatzlos):
  Flex-Container `<div class="gdtf-cell">` mit:
  1. dem Select `sel-gdtf` (wie bisher per Change-Delegation an `set_gdtf`):
     - Platzhalter-Option `— nicht zugeordnet —` (value ``""``; ersetzt den
       bisherigen Text „— kein Treffer —"),
     - Synthetic-Option für eine Zuordnung außerhalb von Kandidaten UND
       Bibliothek (Bestandslogik, bleibt als Sicherheitsnetz),
     - `<optgroup label="Vorschl&auml;ge">` mit den Kandidaten (Reihenfolge
       wie bisher, nur wenn Kandidaten existieren),
     - `<optgroup label="Gesamte Bibliothek">` mit allen `library.files`,
       die NICHT bereits als Kandidat gelistet sind (alphabetisch, wie vom
       Backend geliefert; Gruppe entfällt, wenn leer).
     - title-Tooltip mit vollem Dateinamen (v0.3-Verhalten) bleibt.
  2. einem Icon-Button `<button class="btn-share-ico btn-share-search"
     data-type-key data-type-name title="Im GDTF Share suchen">` mit
     Globus-Icon (`iconSpanHtml("globe", "ic-15 ic-blue300")`) — die
     bestehende tbody-Click-Delegation auf `.btn-share-search` öffnet damit
     das vorhandene Suchmodal; KEINE neuen Listener.

### Modus-Zelle (`modeCellHtml`)

Modusliste: `candidate ? candidate.modes : type.assigned_modes` — der
bisherige Ein-Element-Fallback aus `assignment.mode_name` bleibt nur als
letztes Sicherheitsnetz, wenn auch `assigned_modes` leer ist.

### CSS (app.css)

```css
.gdtf-cell { display: flex; align-items: center; gap: 6px; }
.gdtf-cell .sel-gdtf { flex: 1 1 auto; min-width: 0; }
.btn-share-ico {
  flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  background: transparent;
  border: 1px solid var(--border-dark);
  border-radius: 3px;
  cursor: pointer;
}
.btn-share-ico:hover { border-color: var(--blue-300); }
.btn-share-ico:focus-visible { outline: 2px solid var(--blue-300); outline-offset: -1px; }
```

(3px-Radius = `--radius-sm` wie Buttons/Inputs laut Design-System.)

## Verhalten / Randfälle

- Auswahl aus „Gesamte Bibliothek" → `set_gdtf` → Backend löst Modi über
  die Bibliothek auf, `assigned_modes` füllt das Modus-Select vollständig;
  Quelle-Badge zeigt „Bibliothek".
- Share-Suche aus einer Zeile mit bestehender Zuordnung: Download ersetzt
  die Zuordnung (Bestandsverhalten von `share_download`).
- Leere Bibliothek + keine Kandidaten: Select enthält nur die
  Platzhalter-Option; der Globus-Button ist der Weg zum Share (Modal
  erklärt Login bei Bedarf — Bestandsverhalten).
- Sehr lange Namen: Select verkürzt, title zeigt den vollen Namen (v0.3).

## Tests

- Reader: `read_mvr` mit progress-Callback → Aufruffolge `(0, N)` …
  `(N, N)` bei N eingebetteten Einträgen; ohne Callback unverändert.
- Api: `load_mvr` emittiert progress-Events mit aufsteigendem `percent`
  (Drossel-Regel: im Sync-Test genügt „mindestens start, ≥1 read-Event,
  match 80/95"); `share_download` emittiert percent-Events (Share-Client
  mit Fake-Response testen, wie die bestehenden share-Tests).
- `GdtfShareClient._request`/`download`: progress-Callback erhält
  monoton wachsende `downloaded_bytes` und das Content-Length-Total.
- F4: `set_removed(True)`-Pfad bleibt wie getestet; UI-seitig Review +
  Smoke (JS). Backend-Zählung unverändert (Bestandstests decken sie).
- `get_state`: `library.files` alphabetisch (casefold) und vollständig;
  `assigned_modes` (a) für Kandidaten-Zuordnung = Kandidaten-Modi, (b) für
  Nicht-Kandidaten-Bibliotheks-Zuordnung = volle Modi aus der Bibliothek,
  (c) leer ohne Zuordnung.
- `set_gdtf` mit Bibliotheksnamen außerhalb der Kandidaten: Zuordnung
  gesetzt, `assigned_modes` im Folge-State gefüllt (Integrationspfad des
  Nutzer-Reports).
- Frontend: Task-Review + Smoke-Check (App-Start ohne JS-Fehler);
  bestehender Tooltip-Guard-Test bleibt grün (der Empty-State-Text
  „kein Treffer in der Bibliothek" ist in keinem Guard-Test verankert —
  verifiziert).
- Version 0.4.0 an allen VIER Stellen (pyproject.toml,
  `mvr_enhancer/__init__.py`, index.html-Header, README-Überschrift
  „Bekannte Grenzen") + die zwei Versions-Assertions in tests.

## Risiken

- Grosse Bibliotheken blähen das Select-HTML pro Zeile auf (N Typen × M
  Dateien Optionen). Bei realistischen Grössen (≤ ~20 Typen, ≤ ~300
  Dateien) unkritisch; Optionen-String wird pro Render einmal gebaut und
  wiederverwendet (Implementierungsdetail im Plan).
- Abweichung vom Design-Handoff: Der Leerzustand der GDTF-Zelle („kein
  Treffer in der Bibliothek" + Button) weicht bewusst ab — die neue
  Anforderung ersetzt ihn durch das einheitliche Select + Globus-Button.
