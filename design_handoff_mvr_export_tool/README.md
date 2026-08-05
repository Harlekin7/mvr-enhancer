# Handoff: MVR Export Tool (Standalone-Desktop-App)

**Ziel-Repo:** `Harlekin7/Vectorworks-Tool-GPA` (Branch-Basis: `m1-5-ui-smoke`)
**Sprache der UI:** Deutsch (informelles „du", siehe Copy unten)
**Plattform:** Windows-Desktop, Dark Theme, Fenster-Referenz 1280×1000

## Overview
Eigenständige Desktop-App für Lichtdesigner: Ein aus Vectorworks exportiertes MVR wird geladen, jedem Fixture-Typ wird eine konkrete GDTF-Datei + DMX-Modus zugeordnet (Score-basierte Vorschläge, Nutzer hat das letzte Wort), und ein bereinigtes, grandMA3-sicheres MVR wird exportiert. Die Backend-Logik existiert bereits im Repo (`app/vectorwatch/parsing/mvr_enricher.py`, `mvr.py`, `gdtf.py`) — dieses Handoff liefert die UI und den Interaktionsfluss dafür.

## About the Design Files
Die HTML-Dateien in diesem Ordner sind **Design-Referenzen** (HTML-Prototypen), kein Produktionscode. Aufgabe: die Designs in der Zielumgebung des Repos **nachbauen** — mit dessen etablierten Patterns. Falls noch kein UI-Framework festgelegt ist: Empfehlung für eine Python-Codebasis ist ein Web-UI-Stack (z. B. Tauri/Electron + React, oder pywebview) — die inline dokumentierten CSS-Werte übertragen sich 1:1. Die HTML-Dateien nicht direkt ausliefern.

## Fidelity
**High-fidelity.** Farben, Typografie, Abstände, Copy und Interaktionen sind final gemeint — pixelgenau nachbauen. Die Demo-Daten (Dateinamen, Fixture-Zahlen, Scores) sind Platzhalter und kommen in der echten App aus dem Parser/Matcher.

## Architektur der UI: Vertikale Akkordeon-Pipeline
Die App ist EIN Fenster, EIN Screen: drei Schritte untereinander (01 Quelle → 02 Matching → 03 Export), verbunden durch eine vertikale Pipeline-Linie mit Knoten. Genau ein Schritt ist „aktiv" (aufgeklappt, groß); die anderen sind auf Titel + einzeilige Zusammenfassung kollabiert. **Kein Scrollen zwischen den Schritten** — das Layout füllt exakt die Fensterhöhe (`height:100vh; overflow:hidden`, Spalte per Flexbox); nur Inhalte, die größer als der Platz sind (Matching-Tabelle, Export-Panel), scrollen intern.

### Pipeline-Rail (linke Spalte, 88px breit)
- Knoten: 44×44px Kreis, `border-radius:999px`, zentriert. Schrift Barlow Condensed 700, 19px, weiß.
- Aktiv: Hintergrund `--blue-600` (#1B6FB0), Glow `--shadow-brand`. Inaktiv: `--navy-700`, 1px Border `rgba(255,255,255,0.18)`.
- Abgeschlossen (nicht aktiv): Check-Icon (Lucide `check`, 20px, `--blue-300`) statt Nummer; Border `--blue-400`.
- Knoten 3 zeigt statt „03" das Icon `arrow-down-to-line`.
- Verbindungslinie: 2px breit, `rgba(255,255,255,0.16)`, durchgehend zwischen den Knoten.
- Übergänge: Hintergrund/Glow 320ms.

### Akkordeon-Mechanik
- Sektionen animieren `flex-grow` (aktiv `1 1 auto`, sonst `0 0 auto`) mit `520ms cubic-bezier(0.16,1,0.3,1)`.
- Inhalt: `max-height` 0↔900px (gleiche Kurve) + Zoom `scale(0.96) translateY(-14px) → scale(1)`, Opacity 360ms, `transform-origin: top left`.
- Überschrift skaliert mit: aktiv 40px (Schritt 1) bzw. 32px (2/3), kollabiert 21px; `font-size`-Transition 420ms.
- Klick auf Titel/Kopf eines Schritts aktiviert ihn (Zustand bleibt erhalten).

## Screens / Schritte

### App-Header (56px, immer sichtbar)
`--navy-950`-Hintergrund, 1px Bottom-Border `--border-dark`, Padding 0 28px. Inhalt: Wordmark „GROH·PA" (Barlow Condensed 700, 22px, letter-spacing 0.06em, weiß) · 1px-Trenner · „MVR EXPORT" (Barlow Semi Condensed 600, 15px, uppercase, `--blue-300`) · rechts: Versions-String in JetBrains Mono 11px („v1.0 · DIN SPEC 15801 · MVR 1.6") + Settings-Icon (`settings-2`, 18px). **Hinweis:** Kein offizielles Logo vorhanden — Wordmark ist Platzhalter, offizielle Logodatei anfragen.

### Schritt 1 · Quelle („QUELL-MVR AUS VECTORWORKS")
Hintergrund: Brand-Bild `assets/backgrounds/hintergrund.jpg` unter Scrim `linear-gradient(180deg, rgba(8,19,31,0.60), rgba(8,19,31,0.92))`, cover/center.
- **Leerzustand:** Dropzone min-height 220px, `2px dashed rgba(255,255,255,0.35)`, Radius `--radius-lg` (10px), Hintergrund `rgba(8,19,31,0.35)`. Icon `upload` 40px `--blue-300`. Titel „MVR-Datei hier ablegen" (18px/600/weiß), Untertitel „oder klicken, um eine Datei zu wählen — die 3D-Szene bleibt unangetastet". Hover: Border `--blue-300`, Hintergrund `rgba(8,19,31,0.55)`, 200ms. Klick öffnet Dateidialog; Drag&Drop akzeptiert `.mvr`.
- **Geladen-Zustand:** Dateikarte (`--surface-card-dark`, 1px `--border-dark`, Radius 10px, `--shadow-md`, Padding 20px 24px): Icon-Tile 52×52 `rgba(92,174,221,0.16)` mit `file-box` 26px; Dateiname in JetBrains Mono 15px/600 weiß; Meta-Zeile 13px muted („Vectorworks 2026 · 84,2 MB · geändert …"); rechts vier Kennzahlen (Wert Barlow Condensed 700 26px weiß, Label 11px uppercase tracked muted): Fixtures / Fixture-Typen / 3D-Meshes / Positionen; „Entfernen"-Button (onDarkOutline, sm). Darunter Sicherheits-Zeile mit `shield-check`: „Geprüft: gehärtetes XML, ZIP-Limits eingehalten, keine übersprungenen Dateien".
- **Immer sichtbar (beide Zustände):** 2-spaltiges Kartengrid (gap 16px):
  - „Zuletzt verwendet": Liste zuletzt geladener MVRs (Dateiname Mono 12,5px weiß + Zeitstempel rechts, 12px muted); Zeilen-Hover `rgba(92,174,221,0.10)`, Radius `--radius-sm`; Klick lädt die Datei.
  - „Was mit deiner Datei passiert": 3 Icon-Zeilen (`box`, `link-2`, `eraser`, je 16px `--blue-300`): „3D-Szene & Positionen bleiben unangetastet" / „GDTF, DMX-Modus und Patch werden korrekt gesetzt" / „Giftelemente & verwaiste GDTFs werden entfernt — grandMA3-sicher".
- **Verhalten:** Nach erfolgreichem Laden springt die App nach ~750ms automatisch zu Schritt 2.
- Kollabiert-Zusammenfassung: `buehne_herbsttour_v4.mvr · 204 Fixtures · 310 Meshes` bzw. „noch keine Datei geladen".

### Schritt 2 · Matching („GDTF-ZUORDNUNG PRO FIXTURE-TYP")
Hintergrund `--navy-900`. Neben dem Titel im aufgeklappten Zustand ein Badge (onDark): „5 von 6 zugeordnet".
- **Intro-Satz** (14px muted, max 720px): „Jeder Typ braucht eine konkrete GDTF-Datei im richtigen DMX-Modus — Vorschläge kommen aus dem Score-Matching, du hast das letzte Wort."
- **Quellen-Leiste** (Karte, Padding 14px 20px, Elemente durch 1px×32px-Trenner): Lokale Bibliothek (Icon `folder-open`; Pfad Mono 12,5px + Dateizahl) · GDTF Share (Icon `globe`; angemeldet: grüner 7px-Punkt + „angemeldet als jan.g" + „abmelden"-Link; abgemeldet: „nicht angemeldet" + „Anmelden"-Button onDarkOutline sm) · Checkbox „Nach Position gruppieren" · rechts Button „Overrides teilen".
- **Matching-Tabelle** (Karte, intern scrollend `overflow:auto`, min-width 900px). Sticky Header (10,5px/600, uppercase, letter-spacing 0.12em, muted, Hintergrund `--navy-900`). Grid-Spalten: `minmax(190px,1.2fr) minmax(230px,1.6fr) 84px minmax(180px,1.1fr) 120px`, Zeilen-Padding 10px 20px, Bottom-Border `--border-dark`. Spalten:
  1. **Fixture-Typ**: Name 14,5px/600 weiß + Meta-Zeile Mono 11,5px muted (Anzahl × Position, z. B. „24× · Traverse 1–3").
  2. **GDTF-Datei**: Select mit Kandidaten (dunkles Select: Hintergrund `--navy-900`, Border `rgba(255,255,255,0.25)`). Kein Treffer → Text „kein Treffer in der Bibliothek" + Button „Im Share suchen". Entfernter Typ → durchgestrichen „wird entfernt" + Button „Doch zuordnen".
  3. **Score**: Badge mit 2 Nachkommastellen. Farben: **≥ 0,90 → success (grün)**, **0,30–0,89 → warning (gelb)**, **< 0,30 → danger (rot)**, kein Score → „–".
  4. **DMX-Modus**: Select. Bei Fallback zusätzlich Label „FALLBACK" (11px/600, uppercase, `--amber-500`) mit Tooltip „Fallback: erster Modus der GDTF".
  5. **Quelle**: Badge — „Bibliothek" (onDark), „Share" (brand-blau), „offen" (danger), „entfernt" (onDark).
  - Problem-Zeilen (offen/Fallback) bekommen Zeilenhintergrund `rgba(92,174,221,0.08)`.
- **Fußnote** mit `info`-Icon: „Nicht zugeordnete Typen werden aus dem Export entfernt — das ist gewollt (Plugboxen & Hilfsobjekte) und steht im Report."
- **Primärbutton** rechts unten: „Weiter: Export vorbereiten" → aktiviert Schritt 3.
- Kollabiert-Zusammenfassung: „5 von 6 Typen zugeordnet · 2 offene Punkte" / „wartet auf Quell-MVR".

### Schritt 3 · Export („PULT-FERTIGES MVR")
Hintergrund `--navy-950`. Layout: Grid `minmax(0,1fr) 340px`, gap 20px. Inhalt scrollt intern (`overflow-y:auto`).
- **Vor dem Export (links):** 4 Stat-Komponenten (198/204 Fixtures gematcht · 12 GDTFs eingebettet · 310 Meshes übernommen · 14 Positionsgruppen). Darunter Warnungs-Stack (max 640px, gap 8px), je Zeile Icon + Text, Padding 10px 14px, Radius `--radius-md` (6–8px):
  - Amber-Warnung: Border `rgba(229,163,43,0.45)`, BG `rgba(229,163,43,0.10)`, Icon `triangle-alert` `--amber-500`. Bsp: „**12× Modus-Fallback:** GLP impression X5 nutzt den ersten Modus der GDTF — bitte in Schritt 2 prüfen."
  - Rot: Border `rgba(214,69,69,0.45)`, BG `rgba(214,69,69,0.10)`, Icon `zap` `--red-500`. Bsp: „**Adress-Kollision:** Universum 4, Kanal 12–24 doppelt belegt (…)."
  - Neutral (Bereinigungsliste): nur 1px `--border-dark`, Icon `list-checks` `--blue-300`: „6 Fixtures entfernt (Plugboxen) · 3 verwaiste GDTFs verworfen · CustomCommands & Position gestrippt · alle Geometry3D-Referenzen vollständig".
- **Export-Panel (rechts, 340px, Karte):** Ziel-Pfad (Label 11px uppercase muted, Pfad Mono 12,5px weiß, `word-break:break-all`) · Zeile „Reproduzierbare UUIDs" + Badge „aktiv" · **Export-Button** (volle Breite, lg): normal = Primary-Blau „Exportieren"; **bei offenen Warnungen: Hintergrund/Border `--amber-500`, Text `--navy-950`, Label „Mit 2 Warnungen exportieren"** · darunter Zeile „Danach: vollständiger Report + Diff zum letzten Export".
- **Nach dem Export:** Grünes Report-Banner (Border `rgba(47,158,110,0.5)`, BG `rgba(47,158,110,0.10)`, Icon `circle-check` 28px `--green-500`): „Export erfolgreich — bereit für grandMA3" + Pfad/Größe/Zeit in Mono. Stats erneut, dann Bereinigungsliste + Amber-Hinweis „2 Warnungen im Report vermerkt: …". Panel rechts: Ausgabepfad, Button „Ordner öffnen" (primary, volle Breite), „Diff zum letzten Export" (onDarkOutline), Link „Neuen Export starten" (setzt exportiert-Zustand zurück, MVR bleibt geladen).
- Kollabiert-Zusammenfassung: „exportiert · heute 11:58" / „bereit · 2 Warnungen" / „wartet auf Matching".

### Footer (immer sichtbar)
`--navy-950`, 1px Top-Border, Padding 14px 28px, 12px muted: „GROH·PA · Veranstaltungstechnik · Buchholz i.d.N." links, rechts Mono „grandMA3-geprüfte Pipeline".

## Interactions & Behavior
- Schritt-Kopf klicken → Schritt wird aktiv (Akkordeon-Animation wie oben; alle Timings/Kurven siehe „Akkordeon-Mechanik").
- MVR geladen → Auto-Advance zu Schritt 2 nach ~750ms.
- „Entfernen" → zurück zu Leerzustand + Schritt 1 aktiv (Auto-Advance-Timer abbrechen; `stopPropagation` gegen den Kopf-Klick).
- „Weiter: Export vorbereiten" → Schritt 3 aktiv.
- Export-Klick → Erfolgsansicht; Knoten 3 bekommt Check.
- Hover generell: Karten-Zeilen `rgba(92,174,221,0.10)`; Buttons gemäß Design System (primary dunkelt `blue-600→blue-700`); Transitions 200ms, Press 120ms.
- Fenster-Resize: Layout bleibt scrollfrei; Tabelle/Export-Bereich scrollen intern.
- Fehler-/Ladezustände des echten Parsers (ungültiges MVR, ZIP-Bomben-Schutz) sind im Prototyp nicht gestaltet — an die Sicherheits-Zeile aus Schritt 1 anlehnen (gehärtetes XML, ZIP-Limits).

## State Management
- `mvrGeladen: boolean` — Quelldatei vorhanden (aus Parser).
- `aktiverSchritt: 1|2|3` — Akkordeon-Zustand.
- `exportiert: boolean` — steuert Report-Ansicht in Schritt 3.
- `gruppieren: boolean` — Tabellen-Gruppierung nach Position.
- `shareAngemeldet: boolean` — GDTF-Share-Session.
- `nurProbleme: boolean` — Tabellenfilter (im Prototyp als Tweak vorhanden; in der App als Filter-Toggle über der Tabelle sinnvoll).
- Abgeschlossen-Logik: Schritt 1 fertig = MVR geladen; Schritt 2 fertig = MVR geladen ∧ (aktiv=3 ∨ exportiert); Schritt 3 fertig = exportiert.
- Daten aus Backend: Fixture-Typen mit Kandidaten-GDTFs + Score, Modi je GDTF, Kennzahlen, Warnungsliste, Bereinigungs-Zusammenfassung, Export-Pfad.
- Persistenz: Liste „Zuletzt verwendet" (Pfad + Zeitstempel), Bibliothekspfad, Share-Login.

## Design Tokens (Groh-P.A. Design System)
Vollständig in `design_system/tokens/*.css` (mitgeliefert). Kernwerte:
- **Flächen:** `--navy-950` #08131F (App/Schritt 1+3), `--navy-900` (Schritt 2), `--surface-card-dark` (Karten), `--border-dark` (Hairlines auf dunkel ≈ rgba(255,255,255,0.08–0.12)).
- **Brand:** `--blue-600` #1B6FB0 (primär/aktiver Knoten), `--blue-300` #5CAEDD (Akzent/Icons), `--blue-100` (Fließtext auf dunkel), `--text-inverse-muted` (Sekundärtext).
- **Status:** `--green-500`/`--status-success` (Erfolg), `--amber-500` #E5A32B (Warnung), `--red-500` #D64545 (Fehler).
- **Typo:** Barlow Condensed 700 uppercase (Headlines; 40/32/21px im Akkordeon), Barlow 400–600 (Body 13–14,5px, line-height ~1.5), Barlow Semi Condensed 600 (Sub-Brand), JetBrains Mono (Pfade, Dateinamen, Specs, Eyebrows 11px letter-spacing 0.10–0.14em uppercase).
- **Radius:** Buttons/Inputs 3px (`--radius-sm`), Warnzeilen `--radius-md`, Karten 10px (`--radius-lg`), Pills 999px.
- **Schatten:** navy-getönt (`--shadow-md`), `--shadow-brand` = blauer Glow für aktive Knoten/Primäraktionen.
- **Spacing:** 4px-Raster; Container max 1240px, Gutter 24px; Rail-Spalte 88px, Gap 20px.
- **Motion:** Standard 200ms `cubic-bezier(0.22,0.61,0.36,1)`; Akkordeon 520ms `cubic-bezier(0.16,1,0.3,1)`; keine Bounces.

## Komponenten aus dem Design System
Button (variants: primary, onDarkOutline; sizes sm/md/lg), Badge (tones: onDark, brand, success, warning, danger), Select (dark), Checkbox (onDark), Stat (onDark), Card. Quellcode unter `design_system/components/`.

## Assets
- `assets/backgrounds/hintergrund.jpg` — Brand-Hintergrund (Schritt 1, unter Navy-Scrim). Mitgeliefert.
- Icons: **Lucide** (~2px Stroke). Verwendet: settings-2, upload, file-box, shield-check, box, link-2, eraser, folder-open, globe, info, check, arrow-down-to-line, triangle-alert, zap, list-checks, circle-check.
- Fonts: Barlow / Barlow Condensed / Barlow Semi Condensed / JetBrains Mono via Google Fonts (Substitute — falls Lizenz-Fonts existieren, tauschen).
- **Logo fehlt** — Wordmark „GROH·PA" ist Platzhalter.

## Files
- `MVR Export App.dc.html` — das Design (alle 3 Schritte, komplette Interaktionslogik im Script am Dateiende; dort stehen auch die exakten Inline-Styles und die Score-Schwellen).
- `MVR Export App (Fenster).dc.html` — Windows-11-Fensterrahmen-Kontext (1280×1000).
- `design_system/` — Tokens (CSS), Komponenten-Quellen, styles.css.
- Zum Ansehen: HTML-Dateien gehören zu einem Prototyp-Werkzeug; maßgeblich sind Markup + Inline-Styles + das `data-dc-script`-Script (React-ähnliche Logik-Klasse).

## Bekannte offene Punkte (nicht Teil dieses Handoffs, als Backlog)
- Score-Legende (Tooltip: grün ≥0,90 sicher · gelb prüfen · rot kein Match)
- GDTF-Share-Suchdialog & Login-Flow
- Integration der lokalen GDTF-Bibliothek (Pfad-Auswahl, Indizierung)
- Detailansicht der Address-Kollisions-Warnung
