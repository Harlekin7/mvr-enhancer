# MVR Enhancer v0.2 — Drag&Drop, Ladebalken, Export-Layer-Modus (Design)

Datum: 2026-08-06 · Status: vom Nutzer freigegeben (Chat) · Basis: v0.1.0 (main, d91de32)

## Ziel

Drei Änderungen aus dem ersten echten Produktiveinsatz:

1. **F1 — Drag&Drop repariert:** Eine .mvr-Datei auf die Dropzone ziehen lädt sie.
2. **F2 — Dropzone als Ladebalken:** Beim Laden (egal ob Drop, Dialog oder
   Zuletzt-Liste) wird die Dropzone zum Fortschrittsbalken, der mindestens
   1 Sekunde von links nach rechts durchläuft.
3. **F3 — Export-Modus-Switch:** Umschalter „Single Layer" / „Per Layer" neben
   „Nach Position gruppieren"; Auswahl persistiert; Default Single Layer.

4. **F4 — App-Icon aus dem Handoff:** `design_handoff_app_icon/` liefert das
   finale Icon (Motiv „3a": MVR-Datei vor Groh-Blau-Lichtdiagonalen, azure
   Haken-Badge) als fertige PNGs (16/24 aus der Small-Variante, 32–256 aus dem
   Master). `tools/make_icon.py` packt künftig **diese** PNGs in
   `build/app.ico` (der bestehende PNG-in-ICO-Packer bleibt), statt den
   „G"-Platzhalter zu rendern. Das Icon-Handoff wird mit committet
   (Reproduzierbarkeit); PyInstaller-Einbindung bleibt unverändert
   (`icon=build/app.ico`). Kein Fenster-Icon zur Laufzeit — auf Windows kommt
   Titelleiste/Taskleiste aus dem .exe-Icon.

Am Ende: Release **v0.2.0** (Versions-Bump in `pyproject.toml`, README-Update,
Tag → Release-Workflow baut die .exe).

## Nicht-Ziele

- Leere Layer in einer **bestehenden** grandMA3-Show löschen: Ein MVR-Import
  kann vorhandene Show-Layer prinzipiell nicht entfernen. Die im Nutzer-Test
  gesehenen leeren Layer stammen aus früheren Importen in dieselbe Show
  (bestätigt). Der Single-Layer-Export enthält bereits genau einen Layer —
  hier gibt es nichts zu fixen, nur zu dokumentieren (README).
- Mehrfach-Datei-Drop (nur die erste .mvr-Datei zählt).
- Fortschritts-Prozentanzeige aus dem Backend (der Balken ist animiert, nicht
  gemessen).

---

## F1 — Drag&Drop-Fix

### Root Cause

pywebview reicht native Dateipfade nur durch, wenn ein **Python-seitiger**
DOM-Drop-Listener registriert ist: `edgechromium.py` verwirft die
`FilesDropped`-Nachricht bei `_dnd_state['num_listeners'] == 0`, und
`num_listeners` wird ausschließlich von `webview.dom.element.Element.on('drop', …)`
erhöht. Unser Drop-Handling ist rein JavaScript — `pywebviewFullPath` ist daher
nie gesetzt, es erscheint nur der Toast „Bitte über den Dialog wählen".

Wichtig: pywebview injiziert `pywebviewFullPath` nur in die **an Python
serialisierte** Event-Kopie (`util.py`), nie in das JS-`File`-Objekt. Ein
JS-seitiger Zugriff darauf kann also grundsätzlich nicht funktionieren — der
Lade-Aufruf muss auf die Python-Seite.

### Lösung

- `main.run()` registriert nach dem Laden des Fensters
  (`window.events.loaded`) einen Drop-Listener:
  `window.dom.get_element('#dropzone').on('drop', api.on_dropzone_drop)`.
- Neue Api-Methode `on_dropzone_drop(event: dict) -> None`:
  - liest `event['dataTransfer']['files']` (Liste von Dicts), nimmt die erste
    Datei mit gesetztem `pywebviewFullPath`, deren Name case-insensitiv auf
    `.mvr` endet;
  - gefunden → `self.load_mvr(path)` (bestehender Pfad, thread-sicher via
    `_run_long`);
  - keine passende Datei → Toast-Event
    `{"type": "toast", "data": {"kind": "info", "text": "Bitte eine .mvr-Datei ablegen"}}`.
  - Der pywebview-Handler läuft in einem eigenen Thread — `load_mvr`/`push`
    sind dafür bereits ausgelegt; die Methode fängt Exceptions selbst
    (Log + Toast), analog zu den übrigen Api-Methoden.
- **app.js:** Der bestehende JS-`drop`-Handler ruft nicht mehr `load_mvr` und
  zeigt keinen Toast mehr — er entfernt nur noch die `drag-over`-Klasse
  (`preventDefault` bleibt, ebenso `dragover`/`dragleave` für die visuelle
  Markierung). Das eigentliche Laden übernimmt der Python-Listener.
- Registrierung defensiv: schlägt `get_element`/`on` fehl (z. B. künftige
  pywebview-Änderung), wird nur geloggt — die App bleibt per Dialog bedienbar.

### Randfälle

- Drop im Geladen-Zustand: Dropzone ist `hidden` und kein Drop-Ziel — kein
  Sonderfall nötig. Der Listener bleibt registriert (Element existiert weiter).
- Ordner oder Nicht-MVR-Datei → Info-Toast wie oben.

---

## F2 — Dropzone als Ladebalken

### Verhalten

- Trigger: Das Backend pusht zu Beginn von `_do_load_mvr` ein Event
  `{"type": "progress", "method": "load_mvr", "data": {"phase": "start"}}`.
  Damit startet der Balken bei **allen** Ladewegen (Drop, Dialog,
  Zuletzt-Liste) und nicht schon beim Öffnen des Datei-Dialogs (Abbrechen
  löst nichts aus).
- Optik: Die Dropzone erhält die Klasse `loading`; eine Füll-Ebene (inneres
  `div#dropzone-fill`) wächst von links nach rechts, Farbe `var(--blue-600)`
  (#1e7cc4) mit reduzierter Deckkraft passend zum Dark Theme; Titeltext
  wechselt auf „Lade …", Untertitel wird ausgeblendet. Icon bleibt.
- Timing (app.js):
  - Bei `phase: "start"`: `loadStartTs = Date.now()`, Füllung animiert per
    CSS-Transition in 1 s auf 90 % und hält dort (Laden dauert ggf. länger).
  - Bei Lade-**Erfolg** (State-Event mit `mvr_loaded: true`): warte
    `max(0, 1000 − (Date.now() − loadStartTs))`, dann Füllung in ~150 ms auf
    100 %, danach normaler UI-Umschlag in den Geladen-Zustand (Filecard).
    Der bestehende sofortige Umschlag wird um genau diese Verzögerung
    aufgeschoben; alle übrigen State-Daten (Tabelle, Stats) rendern wie
    bisher.
  - Bei Lade-**Fehler**: Klasse `loading` entfernen, Füllung zurücksetzen,
    Dropzone zeigt wieder den Normalzustand; Fehler-Toast wie heute.
  - Ein erneuter Ladevorgang während einer laufenden Animation setzt den
    Timer zurück (letzter gewinnt).
- Reine Frontend-Umsetzung (CSS in `app.css`, Logik in `app.js`) plus das
  eine `progress`-Event im Backend.

---

## F3 — Export-Layer-Modus

### Semantik

- **Single Layer** (Default, heutiges Verhalten): Ein Layer
  „MVR Enhancer Export" enthält alles — Fixtures (optional in
  Positions-Gruppen) plus ein GroupObject „3D" mit allen
  Nicht-Fixture-Elementen. Original-Layer erscheinen nicht im Export.
- **Per Layer**: Alle Fixtures wie gehabt im Layer „MVR Enhancer Export"
  (Positions-Gruppierung unverändert wirksam), aber dort **ohne**
  3D-GroupObject. Zusätzlich bleibt jeder Original-Layer, der mindestens ein
  Nicht-Fixture-Element enthält, mit Original-**UUID**, -**Name** und
  -**Matrix** erhalten; sein ChildList enthält genau ein GroupObject
  `name="3D"`, `uuid = uuid5(_NS, f"group_3D_{original_layer_uuid}")`, das die
  Nicht-Fixture-Elemente dieses Layers trägt (erscheint in grandMA3 als
  Grouping-Fixture). Original-Layer ohne Nicht-Fixture-Elemente entfallen.
- Reihenfolge im XML: zuerst „MVR Enhancer Export", dann die Original-Layer
  in Originalreihenfolge.
- Fixtures, die in opaken Nicht-Fixture-Elementen verschachtelt sind (z. B.
  `<Fixture>` in `<SceneObject>`), reisen wie bisher unverändert mit ihrem
  Element mit — in Per-Layer-Modus also im 3D-Grouping ihres Original-Layers.
  `compute_gdtf_references` bleibt dadurch modus-unabhängig korrekt.

### Reader: Layer-Provenienz

`mvr_reader` weiß heute nicht, aus welchem Layer ein Nicht-Fixture-Element
stammt. Neu:

```python
@dataclass
class MvrLayerInfo:
    uuid: str            # Original-uuid roh aus dem Attribut ("" wenn fehlend)
    name: str            # Original-name roh aus dem Attribut ("" wenn fehlend)
    matrix_text: str | None   # Text des direkten <Matrix>-Kinds, sonst None
    non_fixture_elements: list[ET.Element]
```

Fallbacks für fehlende Werte wendet erst der **Enricher** beim Bauen an (das
uuid5-Namespace `_NS` lebt dort): fehlende uuid →
`uuid5(_NS, f"layer_orig_{index}")`, fehlender Name → `f"Layer {index + 1}"`,
fehlende Matrix → Identitätsmatrix.

- `MvrScene` erhält `layers: list[MvrLayerInfo]` (default leer). Die
  bestehende flache Liste `non_fixture_elements` bleibt unverändert erhalten
  (Single-Modus, Stats und `compute_gdtf_references` nutzen sie weiter);
  die `MvrLayerInfo`-Einträge referenzieren **dieselben** Element-Objekte.
- Nicht-Fixtures aus verschachtelten GroupObjects werden dem umgebenden
  Layer zugeordnet (die bestehende Rekursion flacht sie bereits — die
  Zuordnung passiert am Layer-Schleifen-Aufruf in `read_mvr`).

### Enricher

- `enrich_mvr(..., layer_mode: str = "single")` und
  `_reorganize_layers(scene, kept_fixtures, group_by_position, layer_mode)`.
- Unbekannter `layer_mode`-Wert → wie `"single"` behandeln (defensiv).
- Deterministische UUIDs wie bisher (uuid5 mit `_NS`), damit Re-Importe in
  grandMA3 stabil bleiben.
- `EnrichReport` unverändert (kein neues Feld nötig); der Export-Dialog/
  Report zeigt weiterhin dieselben Kennzahlen.

### Settings / API / UI

- `Settings.export_layer_mode: str = "single"` — Werte `"single"` |
  `"per_layer"`; beim Laden wird jeder andere Wert auf `"single"`
  normalisiert; in `save()`-Payload aufnehmen.
- `Api`: Feld `self._layer_mode` (aus Settings initialisiert, auch im
  Startup-Reload), `get_state()["data"]` erhält Schlüssel
  `layer_mode: str`; neue Methode `set_layer_mode(mode: str) -> dict`
  (Spiegel von `set_grouping`: validieren, Lock, Settings speichern, State
  zurück). `run_export` reicht den Modus als Snapshot an `enrich_mvr`
  weiter (wie `grouping_snapshot`).
- **UI:** Rechts neben der Checkbox „Nach Position gruppieren" (nach einem
  `v-sep`-Trenner, vor `sources-bar-right`) ein zweigeteilter
  Segment-Schalter:
  Label „Export:" + zwei Buttons „Single Layer" | „Per Layer" (Segmented
  Control im Stil der bestehenden `btn-outline`-Buttons; aktives Segment
  mit `--blue-600`-Hintergrund). Klick → `callApi("set_layer_mode", value)`;
  Renderer setzt das aktive Segment aus `state.layer_mode`. Tastatur:
  normale Buttons, kein Custom-Widget.
- **README:** Abschnitt zu den zwei Export-Modi + Hinweis „Ein MVR-Import
  kann vorhandene grandMA3-Show-Layer nicht löschen; leere Layer in einer
  Show stammen aus früheren Importen."

---

## Tests

- **Reader:** Ein Test-MVR mit zwei Layern (mit/ohne Matrix, verschachteltes
  GroupObject) → `scene.layers` enthält korrekte uuid/name/matrix_text und
  die richtigen Elemente; `non_fixture_elements` unverändert flach;
  Identität der Element-Objekte zwischen beiden Sichten.
- **Enricher Single:** bestehende Tests bleiben grün (Signatur-Default).
- **Enricher Per Layer:** Export-Baum enthält „MVR Enhancer Export" (ohne
  3D-Gruppe) + Original-Layer mit Original-uuid/name/matrix und je genau
  einem GroupObject „3D" mit deterministischer uuid; Layer ohne 3D-Inhalt
  fehlen; Reihenfolge korrekt; unbekannter Modus fällt auf single zurück.
- **Settings:** Roundtrip `export_layer_mode`; ungültiger Wert → `"single"`.
- **Api (sync):** `set_layer_mode` validiert/persistiert und erscheint in
  `get_state`; `run_export` reicht den Modus durch (Assertion am erzeugten
  XML). `on_dropzone_drop` mit Fake-Event-Dicts: .mvr mit Pfad → Laden;
  ohne `pywebviewFullPath`/falsche Endung → Toast, kein Laden.
- **F2** ist UI-Verhalten (JS/CSS) — manuelle Prüfung; das neue
  `progress`-Event bekommt einen Api-Test (Event wird beim Laden gepusht).

## Risiken

- pywebview-DOM-API (`window.dom`, `Element.on`) ist der offizielle, aber
  wenig genutzte Pfad; der Fix wird vor dem Release manuell in der gebauten
  .exe verifiziert (echte Datei auf die Dropzone ziehen).
- Per-Layer-Export vergrößert das XML nicht nennenswert (nur Layer-Hüllen);
  ZIP-Limits unberührt.
