# Changelog

Alle nennenswerten Änderungen des MVR Enhancers, neueste Version zuerst.
Die Abschnitte sind 1:1 als Beschreibungstexte der [GitHub-Releases](https://github.com/Harlekin7/mvr-enhancer/releases) gedacht.

## v1.0.2 — 2026-08-26

### Behoben
- **Astera-Fixtures kamen in grandMA3 nicht an:** GDTF Share schreibt die Revision in den Dateinamen und kodiert Sonderzeichen dabei URL-artig. Asteras Revision heißt „tested by Astera / V3" — der Schrägstrich lag also als `%2F` im Dateinamen. Beim Export wurde der Name komplett dekodiert, wodurch aus dem `%2F` ein echter `/` wurde. Im ZIP ist das ein Pfadtrenner: die GDTF landete in einem Unterordner statt flach im Archiv-Root, und der `GDTFSpec`-Verweis trug denselben Schrägstrich mit. grandMA3 konnte die Datei dadurch nicht auflösen und hat sämtliche Fixtures dieser Typen beim Import verworfen — im Referenzprojekt betraf das 22 von 39 Fixtures (AX9 PowerPAR, FP6 HydraPanel, FP3 Hyperion Tube). Fixture-Typen ohne Schrägstrich in der Revision waren nie betroffen. Pfadtrenner werden jetzt zu `_` geglättet, sodass jede GDTF flach im Archiv-Root liegt.

## v1.0.1 — 2026-08-12

### Behoben
- **Titelleiste startet sofort dunkel:** Auf Windows 10 blieb die Titelleiste nach dem Start weiß, bis man einmal ins Fenster klickte. Der Dunkel-Modus wird jetzt schon vor dem ersten Anzeigen des Fensters gesetzt, und ein erzwungenes Neuzeichnen sorgt dafür, dass die Leiste auch ohne Klick sofort dunkel ist.

## v1.0.0 — 2026-08-12

### Neu
- **VectorWatch-Abgleich:** Läuft [VectorWatch](https://github.com/Harlekin7/Vectorworks-Tool-GPA) auf demselben Rechner, übernimmt der Enhancer beim Laden einer MVR automatisch das dort bereits gepflegte GDTF-Matching. Er sucht das Projekt, dessen Name zur MVR-Datei passt, prüft über den Fixture-Bestand, ob es wirklich dazugehört (mindestens 70 % der Typen müssen bekannt sein), und übernimmt dann Zuordnungen und DMX-Modi — Quelle „VectorWatch" in der Matching-Tabelle. Fehlende GDTF-Dateien werden aus der VectorWatch-Bibliothek in die eigene kopiert; ein in VectorWatch bewusst gesetztes „kein Match" bleibt unzugeordnet. Alles läuft rein lesend im Hintergrund: ohne VectorWatch-Installation oder passendes Projekt verhält sich die App exakt wie bisher. Eine Hinweiszeile in Schritt 2 zeigt das Ergebnis; abschaltbar in der Quellen-Leiste.
- **Dunkle Titelleiste auf jedem Windows:** Titelleiste und Fensterrahmen passen jetzt auch auf Windows 10 zum Dark Theme der App (bisher nur Windows 11); ab Windows 11 werden sie exakt auf die App-Hintergrundfarbe gesetzt — unabhängig vom Hell/Dunkel-Modus des Systems.

## v0.5.0 — 2026-08-06

### Neu
- **Bibliotheks-Picker:** Der Buch-Button neben jedem GDTF-Dropdown öffnet eine durchsuchbare Liste der kompletten Bibliothek. Das Dropdown selbst zeigt dafür nur noch die Score-Vorschläge und bleibt übersichtlich — auch bei großen Bibliotheken.

## v0.4.0 — 2026-08-06

### Neu
- **Freie GDTF-Zuordnung:** Jede Zeile der Matching-Tabelle kann jetzt jede GDTF der Bibliothek zugewiesen bekommen — nicht mehr nur die Score-Vorschläge. Zusätzlich gibt es die Share-Suche direkt an jeder Zeile (Globus-Button) und den expliziten Eintrag „— aktiv entfernt —" im Dropdown.
- **Echter Ladefortschritt:** Der Ladebalken beim MVR-Laden und beim Share-Download folgt dem tatsächlichen Fortschritt statt einer Animation.

### Behoben
- Der 30-Sekunden-Watchdog der UI misst jetzt Stille statt Gesamtdauer — große Dateien lösen keinen falschen Timeout mehr aus, solange Fortschritt gemeldet wird.

## v0.3.0 — 2026-08-06

### Neu
- **Tooltips überall:** Alle Bedienelemente, Scores, Quellen-Badges, Statistiken und Pfade erklären sich jetzt per Tooltip (inkl. Score-Legende: ab 0.90 sicher, 0.30–0.89 prüfen, unter 0.30 unwahrscheinlich).

### Entfernt
- Die Platzhalter „Overrides teilen" und „Diff zum letzten Export" sind bewusst gestrichen.

## v0.2.0 — 2026-08-06

### Neu
- **Export-Modi:** Umschalter „Single Layer" (alles in einem Layer „MVR Enhancer Export") und „Per Layer" (3D-Objekte bleiben in ihren Original-Layern, je mit eigener 3D-Gruppe).
- **Drag & Drop:** MVR-Dateien können direkt auf die Ablagefläche gezogen werden.
- **Ladebalken:** Die Ablagefläche wird während des Ladens zum Fortschrittsbalken.
- App-Icon aus dem Design-Handoff.

## v0.1.0 — 2026-08-06

Erste Version. Der komplette Drei-Schritte-Workflow:

- **Quelle:** MVR laden (Dateidialog oder Zuletzt-Liste) mit Datei-Kennzahlen und Sicherheitsprüfung (gehärtetes XML, ZIP-Limits, Pfad-Traversal-Schutz).
- **Matching:** Score-basierte GDTF-Vorschläge aus der lokalen Bibliothek, DMX-Modus-Auswahl, GDTF-Share-Anbindung (Login, Suche, Download) mit DPAPI-verschlüsseltem Passwort.
- **Export:** grandMA3-sicheres MVR — Gift-Elemente (`CustomCommands`, `Position`) entfernt, verwaiste GDTFs verworfen, Layer nach Position reorganisiert, Warnungen (Modus-Fallbacks, Adress-Kollisionen) und Bereinigungs-Vorschau vor dem Export, vollständiger Report danach. Reproduzierbare UUIDs, damit grandMA3 Re-Importe wiedererkennt.
- Windows-Build als portable `MVR Enhancer.exe` (PyInstaller, CI-Release-Workflow).
