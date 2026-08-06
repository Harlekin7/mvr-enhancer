# App-Icon Handoff — MVR Export Tool

Finales Icon (Auswahl "3a"): bestehende MVR-Datei vor den Groh-Blau-Lichtdiagonalen,
azure Haken-Badge = geprüft & veredelt (nicht neu erzeugt).

## Dateien
- app-icon.svg — Master (Detailversion, für ≥ 32 px; Quelle für alle Renderings)
- app-icon-small.svg — vereinfachte Pixel-Variante (für 16/24 px: dickere Striche, keine Beams, keine Datei-Faltung)
- png/ — fertige Renderings: 256, 128, 64, 48, 32 (Master) · 24, 16 (Small)

## ICO bauen (Windows)
Alle PNGs in eine .ico packen, z. B.:
  magick png/app-icon-16.png png/app-icon-24.png png/app-icon-32.png png/app-icon-48.png png/app-icon-64.png png/app-icon-128.png png/app-icon-256.png app-icon.ico
Windows wählt pro Kontext (Titelleiste 16, Taskleiste 24/32, Alt-Tab 48, Explorer 256) automatisch die passende Größe.

## Verwendung
- Titelleiste & Taskleiste: die Small-Variante (16/24) ist Pflicht — die Master-Geometrie matscht unter 32 px.
- Keine weiteren Farb-/Formvarianten anlegen; monochrome Kontexte: Datei+Haken in Weiß auf transparent aus app-icon-small.svg ableiten.

## Farben (Groh-P.A. Design System)
- Hintergrund: Verlauf #0D2A45 → #08131F (navy)
- Beams: Verlauf #5CAEDD → #1B6FB0 ("Groh Blau"), Opazitäten 0.25–0.55, Rotation 32°
- Datei-Outline: #FFFFFF · Badge: #5CAEDD · Haken im Badge: #08131F
- Eckenradius Tile: 13/64 der Kantenlänge (≈ 20 %)
