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

## Ziel

Jede Matching-Zeile erlaubt (a) die Auswahl JEDER GDTF aus der lokalen
Bibliothek und (b) den Sprung ins Share-Suchmodal — unabhängig davon, ob
und wie viele Kandidaten es gibt. Die Modus-Auswahl zeigt immer die volle
Modusliste der zugeordneten GDTF. Release **v0.4.0**.

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
