# Design-Review gegen den Prototyp (Task 14)

Abgleich der gebauten UI (`mvr_enhancer/ui/`) gegen das Design-Handoff:

- `design_handoff_mvr_export_tool/MVR Export App.dc.html` — der Prototyp, **pixel-maßgeblich**
- `design_handoff_mvr_export_tool/README.md` — die Spezifikation
- `design_handoff_mvr_export_tool/design_system/` — Tokens + Komponenten-Quellen

## Methode

Beide Seiten wurden bei **1280×1000** in Edge (`--headless=new`) gerendert und Zustand
für Zustand nebeneinander verglichen (Screenshots + gemessene `getBoundingClientRect()`-
und `getComputedStyle()`-Werte für Header, Rail-Knoten, Titel-Größen, Sektionshöhen).

- **App:** eine Wegwerf-Harness spielt echte `get_state()`-Payloads (aus `Api(sync=True)`
  mit `demo/quelle.mvr` + `demo/gdtf-library`) via `app.onEvent({type:"state", …})` in die
  unveränderte `app.js`. Der Browser-Modus allein zeigt nur den Leerzustand.
- **Prototyp:** Kopie mit auf `design_system/` umgebogenen `_ds`-Links, aus den
  `.jsx`-Quellen rekonstruiertem `_ds_bundle.js` (Button/Badge/Card/Select/Checkbox/Stat)
  und einem Hash-gesteuerten Start-State, um `aktiv`/`mvr`/`exportiert` zu setzen.

**Verglichene Zustände:** S1 leer · S1 geladen · S2 (Tabelle, Share angemeldet) ·
S3 vor Export (Warnungen) · S3 nach Export · Login-Modal · Share-Suche-Modal ·
S2 mit gescrollter Tabelle (Sticky-Header-Check).

Die finalen Screenshots liegen in `docs/screenshots/`.

## Gefundene Abweichungen und Fixes

### 1. Icons wurden nie angezeigt (Bug)

`assets/icons.js` deklarierte `const ICONS = {…}`. Ein Top-Level-`const` landet im
Skript-Scope, **nicht** auf `window` — `bootstrapIcons()` (`app.js`) liest aber
`window.ICONS` und setzte deshalb bei *jedem* `render()` alle `[data-icon]`-Spans auf
`innerHTML = ""`. Ergebnis: kein einziges Lucide-Icon in der ganzen App (Upload,
Settings, Shield-Check, Rail-Checks, Warn-Icons, Modal-Schließer …).

*Fix:* `window.ICONS = {…}` in `mvr_enhancer/ui/assets/icons.js` und im Generator
`tools/fetch_assets.py`.

### 2. Matching-Tabelle: Spaltenlücken zerschnitten Zeilen und Sticky-Header

Padding, Hairline, Hintergrund und `position:sticky` saßen auf den Zellen. Weil die
Zeile ein Grid mit `gap: 0 16px` ist, schien in jeder Lücke die Kartenfläche durch:
der Sticky-Header wirkte als vier senkrecht getrennte Blöcke, die Zeilen-Unterkante
war unterbrochen. Zusätzlich verschoben die je 20px Zellen-Innenabstände die Spalten
gegenüber dem Prototyp (GDTF-Spalte bei 439px statt 427px).

*Fix:* `padding: 10px 20px`, `border-bottom` und Sticky/Background auf `tr`
(`thead tr`) verlegt, Zellen auf `padding: 0; min-width: 0`. Spalten liegen jetzt
deckungsgleich; Sticky-Header verifiziert (gescrollte Tabelle).

### 3. „FALLBACK" brach unter das DMX-Modus-Select

`.modus-cell` hatte `flex-wrap: wrap`, das Select `width: 100%` — das Label rutschte in
eine zweite Zeile und machte betroffene Tabellenzeilen 82px statt 65px hoch. Im
Prototyp schrumpft das Select und das Label steht daneben.

*Fix:* `flex-wrap: nowrap` + `min-width: 0` auf dem Select in `.modus-cell`.

### 4. Abstand Dateikarte → Sicherheitszeile war 12px statt 28px

Im Prototyp sind Karte und Zeile Geschwister in der 16px-Gap-Flex-Spalte, die Zeile hat
zusätzlich `margin-top: 12px`. In der App umschließt `#filecard-block` beide, wodurch
nur die 12px blieben.

*Fix:* `.filecard-block { display: flex; flex-direction: column; gap: 16px; }`

### 5. Dropzone 220px statt 288px hoch

Der Prototyp hat **keinen** `box-sizing: border-box`-Reset, sein `min-height: 220px` ist
also eine *Content*-Höhe: gerendert 220 + 2×32 Padding + 2×2 Border = **288px**. Unser
globaler Reset machte daraus 220px Gesamthöhe — der Hero-Bereich des Leerzustands wirkte
gestaucht. Prototyp ist pixel-maßgeblich.

*Fix:* `box-sizing: content-box` auf `.dropzone` (mit Kommentar) — reproduziert das
Box-Modell des Prototyps exakt, ohne die dokumentierte 220 zu verfälschen.

Der Unterschied betrifft nur die Dropzone: alle anderen Elemente mit fixer Höhe im
Prototyp haben kein vertikales Padding (Header 56px, Knoten 44px, Icon-Tile 52px,
Trenner 32px), und `<button>` ist in Chrome per UA-Stylesheet ohnehin `border-box`
(DS-Buttons rendern also in beiden Fassungen 36/44/54px).

### 6. Zusätzlicher „Datei wählen…"-Button in der Dropzone

Der Prototyp hat dort keinen Button, und der Untertitel verspricht die Klick-Aktion
schon („oder klicken, um eine Datei zu wählen …").

*Fix:* Button entfernt. Damit die Tastaturbedienung nicht verloren geht, ist die
Dropzone jetzt `role="button" tabindex="0"` mit Enter/Space-Handler und
`:focus-visible`-Rahmen.

### 7. Stat-Werte in Schritt 3 zu klein (28px)

Die DS-Komponente `Stat` rendert den Wert mit `clamp(44px, 6vw, 72px)`; im Prototyp sind
das bei 1280px Fensterbreite 72px — dort brechen die vier Stats dann auf zwei Zeilen um
und schieben den Warnungs-Stack nach unten (der Prototyp bricht an dieser Stelle sein
eigenes Layout, `hint-size="auto,80px"` zeigt, dass eine Zeile gemeint war). 28px war
umgekehrt deutlich zu leise für einen „big numeric proof-point".

*Fix:* `44px` — die Untergrenze der DS-Rampe. Vier Stats passen in eine Zeile, die
optische Gewichtung entspricht dem Prototyp. Zusätzlich
`letter-spacing: var(--tracking-display)` wie in `Stat.jsx`.

### 8. Nach dem Export blieb die vollständige Warnungsliste stehen

Prototyp und README (§Schritt 3, „Nach dem Export") zeigen dort nur noch die
Bereinigungsliste **plus eine** Amber-Zeile „N Warnungen im Report vermerkt: …".

*Fix:* `renderExportedWarnStack()` in `app.js`; `renderWarnStack()` teilt sich die
Bereinigungszeile jetzt über `cleanupRowHtml()`.

### 9. Kleinigkeiten

- `.export-panel-post`: `gap: 12px` statt 14px (Prototyp nutzt im Nach-Export-Panel 12px).
- Modal-Overlay: `var(--surface-overlay)` statt hart kodiertem `rgba(8,19,31,0.7)` (Token = 0.72).

## Nachtrag: globale 75%-Skalierung (Nutzerwunsch)

Auf Wunsch skaliert die gesamte App auf **75%**. Umgesetzt als `html { zoom: 0.75 }`
in `css/app.css`; das Fenster (`main.py`) ist entsprechend **960×777** statt 1280×1036,
`min_size` **830×620** statt 1100×800.

**Die Pixelwerte aus dem Handoff bleiben unverändert** — es ist bewusst *keine*
Neuberechnung der Layout-Werte, sondern eine Skalierung der Darstellung. `zoom` (nicht
`transform: scale`) weil es umbricht: die Root-`zoom` teilt den Initial Containing Block
durch den Faktor, ein 960px breites Fenster rechnet also weiterhin gegen ~1280 logische
px — das Layout ist damit **identisch** zum 1280er Referenz-Rendering, nur kleiner.

`zoom` sitzt auf `html`, nicht auf `#app`: Modal-Overlays und der Toast-Stack sind
Geschwister von `#app` und müssen mitskalieren, während ihr `position: fixed; inset: 0`
weiter den ganzen Viewport deckt. `#app` nutzt jetzt `height: 100%` statt `100vh` —
Viewport-Einheiten werden von der Root-`zoom` *nicht* geteilt, `100vh` hätte unter
`zoom: 0.75` ein Viertel des Fensters leer gelassen.

Verifiziert per Headless-Edge-Screenshot bei 960×777 (S1/S2/S3, vor & nach Export,
Leerzustand) gegen die 1280×1000-Referenzen in `docs/screenshots/` — deckungsgleiche
Anordnung, gleiche Umbrüche.

### Nachtrag: Layout-Kollaps bei minimaler Fenstergröße behoben

Bei minimaler Fenstergröße überschrieb der Body der *aktiven* Sektion (`flex: 1 1 auto`,
schrumpft) die Sektionsköpfe darunter — die Akkordeon-Navigation war damit unerreichbar.
`.sect` bekommt jetzt `overflow: hidden` (Clipping statt Überzeichnen) und
`min-height: 96px`, `.sect-head` zusätzlich `min-height: 44px` (Eyebrow 11px + 6px +
Titel 21px×1.2), damit eine geschrumpfte Sektion nicht ihren eigenen Kopf abschneidet.
Verifiziert per Headless-Screenshot bei 830×620 mit jeweils Sektion 1, 2 und 3 aktiv:
alle drei Köpfe sichtbar.

### Nachtrag: Wartezustände (Spec-Vorgabe)

Ohne geladenes Quell-MVR zeigt `#match-tbody` eine einzelne Platzhalterzeile
„wartet auf Quell-MVR" und `#btn-continue` ist deaktiviert; der Hauptteil von Schritt 3
zeigt „wartet auf Matching" (statt einer 0/0-Kennzahlenzeile) und `#btn-export` ist
deaktiviert.

## Geprüft und in Ordnung

- **Header:** 56px, Wordmark Barlow Condensed 700/22px/0.06em, 1px-Trenner, Subbrand
  Barlow Semi Condensed 600/15px/**0.04em** uppercase `--blue-300`, Versions-String
  JetBrains Mono 11px, Settings-Icon `settings-2` 18px in **`--blue-200`** — alle
  offenen Ledger-Punkte hierzu deckungsgleich mit dem Prototyp.
- **Rail:** Knoten 44×44px, aktiv `--blue-600` (#1e7cc4) + `--shadow-brand`, erledigt
  = Check-Icon 20px `--blue-300` mit `--blue-400`-Rand, Knoten 3 `arrow-down-to-line`,
  Linie 2px `rgba(255,255,255,0.16)`. Positionen messgleich (x49, 44×44).
- **Akkordeon:** Titelgrößen gemessen 40 / 32 / 21px, `line-height` 1.05 in Schritt 1;
  Schritt 1 wächst nicht (`flex: 0 1 auto`), Sektionshöhen kollabiert identisch
  (105px / 117px); Timings 520ms `cubic-bezier(0.16,1,0.3,1)`, 420ms Font-Size, 320ms Knoten.
- **S1:** Dateikarte (Tile 52px, Mono 15px, vier Kennzahlen Barlow Condensed 700/26px),
  Sicherheitszeile, 2-Spalten-Kartengrid, Hintergrundbild + Scrim
  `linear-gradient(180deg, rgba(8,19,31,.60), rgba(8,19,31,.92))` — deckungsgleich.
- **S2:** Quellen-Leiste (Icons 17px, Labels 11px/0.1em, grüner 7px-Punkt, Checkbox,
  32px-Trenner), Spaltenraster `minmax(190px,1.2fr) minmax(230px,1.6fr) 84px
  minmax(180px,1.1fr) 120px`, Badge-Töne (success/warning/danger/onDark/brand),
  Score-Schwellen ≥0.90 / ≥0.30, Problemzeilen-Tint `rgba(92,174,221,0.08)`, Fußnote,
  Primärbutton.
- **S3:** Warnzeilen (Amber `rgba(229,163,43,.45)/.10`, Rot `rgba(214,69,69,.45)/.10`,
  Neutral `--border-dark`), Export-Panel 340px, Amber-Export-Button
  (`--amber-500` auf `--navy-950`), Report-Banner grün mit `circle-check` 28px.
- **Footer:** `--navy-950`, 1px Top-Border, 14px/28px Padding, 12px, Copy links/rechts.
- **Copy:** alle Texte wörtlich gegen den Prototyp geprüft (Eyebrows, Titel, Dropzone,
  Intro-Satz, Fußnote, Warn-Formulierungen, Kollabiert-Zusammenfassungen, Footer).
- **Amber-Hover/Press** `#cf9422` / `#b9821c`: im Prototyp nicht gestaltet. Gleiche Hue
  (39°), monoton fallende Helligkeit (53% → 47% → 42%) — plausibel, bleibt.
- **Modals:** stilistisch kohärent mit dem Design System (dunkle Karte, Barlow
  Condensed uppercase Titel, `--tracking-label`-Labels, Primary/Outline-Buttons,
  Mono-Ergebnisnamen).

## Bewusst beibehaltene Abweichungen

| Abweichung | Begründung |
| --- | --- |
| Dunkle Selects (`--navy-900`, Border `rgba(255,255,255,.25)`) | Der Prototyp rendert **weiße** Felder mit dunklem Text — die DS-`Select` bekommt `onDark` nicht gesetzt. Auf navy-Grund ist das ein Fehler, und der README schreibt explizit „dunkles Select" vor. Bereits in Spec §5 festgehalten. |
| Badges/Zusammenfassungen berechnet („3 von 5 zugeordnet") | Prototyp-Zahlen („5 von 6", „204 Fixtures", „12× Modus-Fallback") sind laut Handoff Platzhalter; echte Werte kommen aus Parser/Matcher. |
| Export-Button blau „Exportieren" ohne Warnungen | Der Prototyp zeigt fest den Amber-Fall. README §Schritt 3: Amber nur „bei offenen Warnungen". |
| Versions-String „v0.1.0 · DIN SPEC 15801 · MVR 1.6" | Echte Paketversion statt der Prototyp-Attrappe „v1.0". |
| Filterzeile „Nur Probleme anzeigen" über der Tabelle | Im Prototyp nur als Tweak vorhanden; README §State Management empfiehlt genau diesen Toggle in der App. |
| Stat-Wert 44px statt 72px | Siehe Fix 7 — 72px bricht das Layout des Prototyps selbst. |
| Dropzone-Button entfernt, Zone tastaturbedienbar | Siehe Fix 6. |
| `#header` / `#footer` mit `flex: none` | Der Prototyp lässt beide schrumpfen; bei vollem Inhalt schrumpft sein Header messbar auf 52px. README: „Header (56px, immer sichtbar)". |
| Modals, Toasts, „Zuletzt verwendet"-Leerzustand, Datei-Dialog-Fehler | Im Prototyp nicht gestaltet (Handoff-Backlog: „GDTF-Share-Suchdialog & Login-Flow"), neu gebaut mit DS-Mitteln. |
| „Overrides teilen" / „Diff zum letzten Export" deaktiviert | Funktionen sind in v1 nicht implementiert. |

## Beobachtung ohne Fix

Bei sehr langen Bibliothekspfaden (z. B. `C:\Dev\MVR Enhancer\demo\gdtf-library`) bricht
„Overrides teilen" in der Quellen-Leiste in eine zweite Zeile um und kostet ~58px
Tabellenhöhe. Das ist das `flex-wrap: wrap`-Verhalten des Prototyps und rein
datenabhängig (mit einem Pfad wie `D:\GDTF-Bibliothek` bleibt es einzeilig) — bewusst
nicht durch `nowrap`/Ellipsis ersetzt, weil das den Pfad abschneiden würde.
