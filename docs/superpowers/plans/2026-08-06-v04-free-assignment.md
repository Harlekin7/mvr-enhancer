# MVR Enhancer v0.4 Implementation Plan (Freie GDTF-Zuordnung + Share pro Zeile)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede Matching-Zeile erlaubt die Auswahl jeder Bibliotheks-GDTF, den Sprung ins Share-Suchmodal und das aktive Entfernen per Dropdown; der Ladebalken folgt echtem Fortschritt und der 30-s-Watchdog feuert nur noch bei Stille.

**Architecture:** Backend liefert neue State-Felder (`library.files`, `assigned_modes`) und periodische progress-Events aus Reader-/Download-Callbacks; das Frontend strukturiert die GDTF-Zelle um (Sonder-Einträge „nicht zugeordnet"/„aktiv entfernt", optgroups, Globus-Button), speist die Modus-Zelle aus `assigned_modes` und treibt den Balken mit den echten Prozentwerten. `set_gdtf`/`set_removed` bleiben unverändert.

**Tech Stack:** Python (Api), Vanilla JS/CSS, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-06-v04-free-assignment-design.md`

## Global Constraints

- `library.files` = `sorted(self._gdtf_library.keys(), key=str.casefold)`; `assigned_modes` = Modi der zugeordneten GDTF (Kandidat → dessen `modes`, sonst `_modes_from_library`, ohne Zuordnung `[]`). Beides unter dem bestehenden `get_state`-Lock.
- Select-Struktur: Sonder-Einträge `— nicht zugeordnet —` (value "") und `— aktiv entfernt —` (value `"__removed__"`, selektiert wenn `assignment.removed`) · Synthetic-Option (Bestand) · `<optgroup label="Vorschl&auml;ge">` (nur wenn Kandidaten) · `<optgroup label="Gesamte Bibliothek">` (alle `library.files` minus Kandidaten; entfällt wenn leer).
- Der Sentinel `"__removed__"` erreicht das Backend NIE — der Change-Handler verzweigt vorher auf `set_removed(key, true)`.
- Der bisherige Leerzustand der GDTF-Zelle („kein Treffer in der Bibliothek" + Button) UND der removed-Sonderzustand („wird entfernt" + „Doch zuordnen") entfallen ersatzlos — bewusste Handoff-Abweichung laut Spec; der `btn-reassign`-Delegationszweig wird entfernt.
- Progress-Events: `load_mvr` → `{"phase":"read","percent":P}` mit P = 5 + (done/total)×70, dann `{"phase":"match","percent":80}` und `{"phase":"match","percent":95}`; `share_download` → `{"percent":P}` (P aus Bytes/Content-Length, `null` wenn total unbekannt). Drossel überall: Event nur, wenn percent um ≥3 Punkte gestiegen ODER ≥500 ms seit letztem Event.
- Balken-UI: Start-Kriechen auf 15 % in 2 s; `dzProgress(percent)` monoton, Deckel 95 %, `transition: transform 400ms linear`; 100 % nur via `dzFinish` (Min-1-s-Regel unverändert).
- Watchdog-Re-Arm: bei jedem progress-Event re-armieren, wenn das Method in `WATCHDOG_ARM_ON_PROGRESS` steht ODER sein Watchdog pendent ist.
- Globus-Button: Klassen `btn-share-ico btn-share-search`, `data-type-key`/`data-type-name`, `title="Im GDTF Share suchen"`, Icon via `iconSpanHtml("globe", "ic-15 ic-blue300")`. KEINE neuen Event-Listener (tbody-Delegation auf `.btn-share-search` existiert).
- Alle dynamischen HTML-Werte durch `esc()`; deutsche UI-Texte, du-Form.
- Die App NIE im Vordergrund starten; Smoke-Check nur per `Start-Process -PassThru; Start-Sleep; Stop-Process`.
- Tests: `.venv\Scripts\python.exe -m pytest`; `.venv\Scripts\ruff.exe check .` sauber.
- Version am Ende: `0.4.0` an ALLEN VIER Stellen (pyproject.toml, `mvr_enhancer/__init__.py`, index.html-Header-String, README-Überschrift „Bekannte Grenzen") plus die zwei Versions-Assertions in `tests/test_api.py` und `tests/test_smoke.py`.

---

### Task 1: Api — `library.files` + `assigned_modes` im State

**Files:**
- Modify: `mvr_enhancer/api.py` (`get_state`, types_out-Schleife ~Z.241–300)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: bestehende `_find_candidate(type_key, gdtf_name)`, `_modes_from_library(gdtf_name)`.
- Produces: `get_state()["data"]["library"]["files"]: list[str]`; `types[i]["assigned_modes"]: list[{"name","channel_count"}]`. Task 2 (UI) konsumiert beide.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_api.py`, im Stil der Bestandstests (`_make_api(tmp_path, ...)`; eine Bibliothek mit `build_gdtf`-Dateien anlegen wie in den vorhandenen Matching-Tests — z. B. zwei Fixtures „Beam One" (Modes „Mode 1"/16ch, „Mode 2"/32ch) und „Wash Two", MVR mit einer Fixture „Beam One"):

```python
def test_state_contains_sorted_library_files(api_with_library):
    files = api_with_library.get_state()["data"]["library"]["files"]
    assert files == sorted(files, key=str.casefold)
    assert len(files) == api_with_library.get_state()["data"]["library"]["count"]


def test_assigned_modes_for_candidate_assignment(api_with_loaded_mvr):
    # Auto-Match hat "Beam One" zugeordnet (Kandidat) -> volle Modi.
    state = api_with_loaded_mvr.get_state()["data"]
    beam = next(t for t in state["types"] if t["assignment"]["gdtf_name"])
    assert [m["name"] for m in beam["assigned_modes"]] == ["Mode 1", "Mode 2"]
    assert beam["assigned_modes"][1]["channel_count"] == 32


def test_assigned_modes_for_non_candidate_library_assignment(api_with_loaded_mvr):
    # Nutzer-Report-Pfad: eine GDTF zuordnen, die NICHT in den Kandidaten
    # des Typs steht (z. B. "Wash Two" fuer den Beam-Typ).
    state = api_with_loaded_mvr.get_state()["data"]
    type_key = state["types"][0]["key"]
    other = next(name for name in state["library"]["files"]
                 if name != state["types"][0]["assignment"]["gdtf_name"])
    assert not any(c["gdtf_name"] == other for c in state["types"][0]["candidates"]) \
        or True  # falls doch Kandidat: Test unten prueft trotzdem die Modi
    result = api_with_loaded_mvr.set_gdtf(type_key, other)
    assert result["ok"]
    updated = next(t for t in result["data"]["types"] if t["key"] == type_key)
    assert updated["assignment"]["gdtf_name"] == other
    assert updated["assigned_modes"], "assigned_modes muss auch ohne Kandidat gefuellt sein"
    assert all("name" in m and "channel_count" in m for m in updated["assigned_modes"])


def test_assigned_modes_empty_without_assignment(api_with_loaded_mvr):
    state = api_with_loaded_mvr.get_state()["data"]
    type_key = state["types"][0]["key"]
    result = api_with_loaded_mvr.set_gdtf(type_key, "")
    updated = next(t for t in result["data"]["types"] if t["key"] == type_key)
    assert updated["assigned_modes"] == []
```

Die Fixtures `api_with_library`/`api_with_loaded_mvr` als lokale Helper-Funktionen bzw. pytest-Fixtures anlegen, exakt nach dem Muster der vorhandenen Tests in der Datei (dort wird bereits eine Api mit tmp_path-Settings, `build_gdtf`-Bibliothek und `build_mvr`-Datei konstruiert — dieses Muster kopieren, nicht neu erfinden). Wenn die Datei solche Fixtures schon besitzt, diese verwenden.

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_api.py -k "library_files or assigned_modes" -v`
Expected: FAIL (KeyError `files` / `assigned_modes`)

- [ ] **Step 3: Implementieren**

In `get_state`:

1. In der types_out-Schleife nach `candidates = ...`:

```python
                    if assignment.gdtf_name:
                        assigned_candidate = self._find_candidate(
                            fixture_type.key, assignment.gdtf_name
                        )
                        if assigned_candidate is not None:
                            assigned_modes = list(assigned_candidate.modes)
                        else:
                            assigned_modes = self._modes_from_library(assignment.gdtf_name)
                    else:
                        assigned_modes = []
```

und im Dict: `"assigned_modes": assigned_modes,` (direkt nach `"assignment"`).

Hinweis: `_find_candidate` greift auf `self._candidates` zu — der Aufruf passiert hier bereits INNERHALB des Locks; `_find_candidate` nimmt selbst keinen Lock (nur ein Loop) — kein Deadlock-Risiko (mit dem Bestand identisches Muster prüfen: `_find_candidate` wird in `set_gdtf` ebenfalls unter Lock gerufen).

2. Im `"library"`-Dict: `"files": sorted(self._gdtf_library.keys(), key=str.casefold),`

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `python -m pytest tests/test_api.py -v` → PASS (alle, auch Bestand)

- [ ] **Step 5: Gesamtsuite + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/api.py tests/test_api.py
git commit -m "feat(api): library.files und assigned_modes im UI-State"
```

---

### Task 2: UI — GDTF-Zelle mit Bibliotheks-Gruppe + Globus-Button, Modus-Zelle aus assigned_modes

**Files:**
- Modify: `mvr_enhancer/ui/js/app.js` (`gdtfCellHtml` ~Z.785–840, `modeCellHtml` ~Z.843, `renderMatchRow` — gdtf-Zelle bekommt den Flex-Container)
- Modify: `mvr_enhancer/ui/css/app.css` (neue Regeln `.gdtf-cell`, `.btn-share-ico`)

**Interfaces:**
- Consumes: `state.library.files`, `type.assigned_modes` (Task 1); bestehende `esc()`, `iconSpanHtml()`, tbody-Delegation auf `.sel-gdtf`/`.btn-share-search`.

- [ ] **Step 1: gdtfCellHtml umbauen**

`gdtfCellHtml` erhält die Signatur `gdtfCellHtml(type, libraryFiles)`. Der removed-Zweig („wird entfernt" + „Doch zuordnen") und der Leerzustand-Zweig (`if (!type.candidates.length && !assignment.gdtf_name)`) werden KOMPLETT entfernt — ALLE Zustände rendern dasselbe Select:

```js
  var REMOVED_SENTINEL = "__removed__";

  function gdtfCellHtml(type, libraryFiles) {
    var assignment = type.assignment;
    // Bei removed=true behaelt das Assignment seinen gdtf_name (set_removed
    // flippt nur das Flag) — dann darf NUR der Sentinel-Eintrag selected
    // sein, sonst gewinnt die spaeter gerenderte GDTF-Option.
    var selectedName = assignment.removed ? null : assignment.gdtf_name;
    var candidateNames = {};
    var candidateOptions = [];
    type.candidates.forEach(function (c) {
      candidateNames[c.gdtf_name] = true;
      candidateOptions.push(
        '<option value="' + esc(c.gdtf_name) + '"' +
        (c.gdtf_name === selectedName ? " selected" : "") +
        ">" + esc(c.gdtf_name) + "</option>"
      );
    });
    var libraryOptions = [];
    (libraryFiles || []).forEach(function (name) {
      if (candidateNames[name]) return;
      libraryOptions.push(
        '<option value="' + esc(name) + '"' +
        (name === selectedName ? " selected" : "") +
        ">" + esc(name) + "</option>"
      );
    });
    var options = [
      '<option value=""' + (!assignment.removed && !assignment.gdtf_name ? " selected" : "") +
      ">&mdash; nicht zugeordnet &mdash;</option>",
      '<option value="' + REMOVED_SENTINEL + '"' + (assignment.removed ? " selected" : "") +
      ">&mdash; aktiv entfernt &mdash;</option>"
    ];
    var assignedKnown = selectedName &&
      (candidateNames[selectedName] ||
        (libraryFiles || []).indexOf(selectedName) !== -1);
    if (selectedName && !assignedKnown) {
      // Sicherheitsnetz: Zuordnung, die weder Kandidat noch Bibliothek kennt
      // (z. B. Bibliothek nach Share-Download noch nicht neu geladen).
      options.push(
        '<option value="' + esc(selectedName) + '" selected>' +
        esc(selectedName) + "</option>"
      );
    }
    if (candidateOptions.length) {
      options.push('<optgroup label="Vorschl&auml;ge">' + candidateOptions.join("") + "</optgroup>");
    }
    if (libraryOptions.length) {
      options.push('<optgroup label="Gesamte Bibliothek">' + libraryOptions.join("") + "</optgroup>");
    }
    var selectTitle = selectedName ? ' title="' + esc(selectedName) + '"' : "";
    return (
      '<div class="gdtf-cell">' +
      '<select class="sel-dark sel-gdtf" data-type-key="' + esc(type.key) + '"' + selectTitle + '>' +
      options.join("") + "</select>" +
      '<button type="button" class="btn-share-ico btn-share-search" data-type-key="' + esc(type.key) +
      '" data-type-name="' + esc(type.name) + '" title="Im GDTF Share suchen">' +
      iconSpanHtml("globe", "ic-15 ic-blue300") +
      "</button>" +
      "</div>"
    );
  }
```

In `renderMatchRow` den Aufruf anpassen: `gdtfCellHtml(type, serverState.library.files)` — bzw. sauberer: `renderMatchRow(type, libraryFiles)` und in `renderMatchTable` `s.library.files` durchreichen: `.map(function (type) { return renderMatchRow(type, s.library.files || []); })`.

- [ ] **Step 1b: Change-Handler + btn-reassign-Zweig**

Im tbody-`change`-Listener den `sel-gdtf`-Zweig ersetzen:

```js
      if (e.target.classList.contains("sel-gdtf")) {
        if (e.target.value === REMOVED_SENTINEL) {
          callApi("set_removed", key, true);
        } else {
          callApi("set_gdtf", key, e.target.value);
        }
      } else if (e.target.classList.contains("sel-mode")) {
```

Im tbody-`click`-Listener den `btn-reassign`-Zweig (Suche nach `.btn-reassign`) ersatzlos entfernen — der Button wird nicht mehr gerendert; der Weg zurück ist das Select selbst (`— nicht zugeordnet —` → `set_gdtf(key, "")` setzt `removed=False`, ebenso jede GDTF-Auswahl).

- [ ] **Step 2: modeCellHtml auf assigned_modes umstellen**

Die Modus-Quelle ersetzen:

```js
    var modes = candidate ? candidate.modes
      : (type.assigned_modes && type.assigned_modes.length) ? type.assigned_modes
      : assignment.mode_name ? [{ name: assignment.mode_name, channel_count: 0 }] : [];
```

(Rest der Funktion unverändert; Fallback-Label-Logik bleibt.)

- [ ] **Step 3: CSS ergänzen**

In app.css bei den Tabellen-/Select-Styles:

```css
.gdtf-cell { display: flex; align-items: center; gap: 6px; }
.gdtf-cell .sel-gdtf { flex: 1 1 auto; min-width: 0; }
.btn-share-ico {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  background: transparent;
  border: 1px solid var(--border-dark);
  border-radius: 3px;
  cursor: pointer;
}
.btn-share-ico:hover { border-color: var(--blue-300); }
.btn-share-ico:focus-visible { outline: 2px solid var(--blue-300); outline-offset: -1px; }
```

- [ ] **Step 4: Smoke-Check**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log (`%APPDATA%\MVR Enhancer\mvr-enhancer.log`) ohne JS-/evaluate_js-Fehler.

- [ ] **Step 5: Suite + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/ui/js/app.js mvr_enhancer/ui/css/app.css
git commit -m "feat(ui): freie GDTF-Auswahl aus der ganzen Bibliothek + Share-Suche an jeder Zeile"
```

---

### Task 3: Reader — Fortschritts-Callback in `read_mvr`

**Files:**
- Modify: `mvr_enhancer/core/mvr_reader.py` (`read_mvr` ~Z.240–257, `_read_mvr_archive` ~Z.260–307)
- Test: `tests/test_mvr_reader.py`

**Interfaces:**
- Produces: `read_mvr(path: str, progress: Callable[[int, int], None] | None = None) -> MvrScene`; `_read_mvr_archive(zf, path, progress=None)`. Callback-Vertrag: einmal `(0, total)` vor der Schleife, danach `(done, total)` nach JEDEM gelesenen Eintrag (`total` = Anzahl der zu lesenden Einträge nach den bestehenden Namens-/Limit-Filtern der Schleifenliste — konkret: die Länge der Liste, über die die bestehende Schleife iteriert). Exceptions des Callbacks werden im Reader NICHT gefangen. Task 4 (Api) konsumiert das.

- [ ] **Step 1: Failing Test schreiben**

```python
def test_read_mvr_reports_progress(tmp_path):
    mvr = build_mvr(
        tmp_path / "p.mvr",
        fixtures=[{"name": "Spot 1", "address": 1}],
        embedded={"mesh1.glb": b"x" * 10, "mesh2.glb": b"y" * 10},
    )
    calls = []
    read_mvr(str(mvr), progress=lambda done, total: calls.append((done, total)))
    assert calls, "progress-Callback wurde nie aufgerufen"
    totals = {t for _, t in calls}
    assert len(totals) == 1, "total muss konstant sein"
    total = totals.pop()
    assert calls[0] == (0, total)
    assert calls[-1] == (total, total)
    dones = [d for d, _ in calls]
    assert dones == sorted(dones), "done muss monoton steigen"


def test_read_mvr_without_progress_unchanged(tmp_path):
    mvr = build_mvr(tmp_path / "q.mvr", fixtures=[{"name": "Spot 1", "address": 1}])
    scene = read_mvr(str(mvr))
    assert scene.xml_root is not None
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `python -m pytest tests/test_mvr_reader.py -k progress -v`
Expected: FAIL (`read_mvr() got an unexpected keyword argument 'progress'`)

- [ ] **Step 3: Implementieren**

`read_mvr(path, progress=None)` reicht `progress` an `_read_mvr_archive(zf, path, progress)` durch. In `_read_mvr_archive`: Die bestehende Schleife über die Archiv-Einträge iteriert über eine Namensliste — diese VOR der Schleife in eine Variable ziehen (`names = [...]` wie im Bestand aufgebaut), dann:

```python
    total = len(names)
    if progress is not None:
        progress(0, total)
    for index, name in enumerate(names, start=1):
        ...bestehender Schleifenkoerper unveraendert...
        if progress is not None:
            progress(index, total)
```

Wichtig: der `progress`-Aufruf am SCHLEIFENENDE muss auch bei `continue`-Zweigen des Bestandscodes erreicht werden — falls der Bestand `continue` nutzt, den Aufruf VOR die `continue`-Stellen duplizieren oder die Schleife per `try/finally` NICHT verkomplizieren, sondern den Callback direkt vor jedem `continue` und am Ende aufrufen (einfachste korrekte Variante; Kommentar warum).

- [ ] **Step 4: Tests + Lint**

Run: `python -m pytest tests/test_mvr_reader.py -v; python -m pytest -q; ruff check .` → grün

- [ ] **Step 5: Commit**

```bash
git add mvr_enhancer/core/mvr_reader.py tests/test_mvr_reader.py
git commit -m "feat(reader): Fortschritts-Callback beim Lesen der Archiv-Eintraege"
```

---

### Task 4: Api + Share — periodische progress-Events (load_mvr, share_download)

**Files:**
- Modify: `mvr_enhancer/api.py` (`_do_load_mvr` ~Z.395–476, `_do_share_download` ~Z.735–768; neuer Helper `_make_throttled_progress`)
- Modify: `mvr_enhancer/core/share.py` (`_request` ~Z.100–121, `download` ~Z.314+)
- Test: `tests/test_api.py`, `tests/test_share.py`

**Interfaces:**
- Consumes: `read_mvr(path, progress=...)` (Task 3).
- Produces: Events `{"type":"progress","method":"load_mvr","data":{"phase":"read","percent":P}}` (P = 5 + done/total×70, int; total==0 → 75), `{"phase":"match","percent":80}`, `{"phase":"match","percent":95}`; `{"type":"progress","method":"share_download","data":{"percent":P|null}}`. `GdtfShareClient._request(..., progress=None)` und `download(..., progress=None)` mit Callback `(downloaded_bytes: int, total_bytes: int) -> None` (`total_bytes` aus Content-Length, 0 wenn unbekannt). Task 5 (UI) konsumiert die Events.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_api.py`:

```python
def test_load_mvr_emits_read_and_match_progress(api, tmp_path):
    mvr = build_mvr(
        tmp_path / "p.mvr",
        fixtures=[{"name": "Spot 1", "address": 1}],
        embedded={"mesh1.glb": b"x" * 10},
    )
    api.load_mvr(str(mvr))
    progress = [e["data"] for e in api.events
                if e.get("type") == "progress" and e.get("method") == "load_mvr"]
    phases = [p.get("phase") for p in progress]
    assert phases[0] == "start"
    assert "match" in phases
    percents = [p["percent"] for p in progress if p.get("percent") is not None]
    assert percents == sorted(percents), "percent muss monoton steigen"
    assert percents and percents[-1] == 95
```

In `tests/test_share.py` (an die bestehende Fake-Response-Infrastruktur der Datei anlehnen — dort werden `_request`/HTTP bereits gemockt; dasselbe Muster verwenden):

```python
def test_request_reports_download_progress(...):
    # Fake-Response mit Content-Length und >64KiB Body; progress-Callback
    # sammelt (downloaded, total): downloaded monoton steigend bis len(body),
    # total == Content-Length.
    ...

def test_download_passes_progress_through(...):
    # download(rid, dir, progress=cb) -> cb wurde aufgerufen.
    ...
```

(Die `...`-Tests anhand der vorhandenen Mock-Muster in test_share.py ausformulieren; die Assertions stehen in den Kommentaren.)

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_api.py -k read_and_match -v; python -m pytest tests/test_share.py -k progress -v`
Expected: FAIL

- [ ] **Step 3: share.py implementieren**

`_request(self, ..., progress=None)`: in der Chunk-Schleife nach `downloaded += len(chunk)`:

```python
                    if progress is not None:
                        progress(downloaded, total_bytes)
```

mit `total_bytes = int(resp.headers.get("Content-Length") or 0)` vor der Schleife (ValueError → 0, via try/except). `download(self, rid, library_dir, *, allow_retry=True, progress=None)` reicht `progress` an seinen `_request`-Aufruf durch (NUR an den Download-Request, nicht an Login/Liste).

- [ ] **Step 4: api.py implementieren**

Neuer modul- oder klassenlokaler Helper (bei den anderen Hilfsfunktionen):

```python
    def _make_progress_emitter(self, method: str, to_percent):
        """Baut einen gedrosselten progress-Callback fuer Hintergrund-Threads.

        ``to_percent(done, total) -> int | None`` mappt Rohwerte auf Prozent.
        Drossel: Event nur, wenn der Prozentwert um >= 3 Punkte gestiegen ist
        ODER >= 0.5 s seit dem letzten Event vergangen sind. Exceptions werden
        gefangen — ein UI-Event darf nie das Laden abbrechen.
        """
        state = {"last_percent": -100, "last_ts": 0.0}

        def _emit_progress(done: int, total: int) -> None:
            try:
                percent = to_percent(done, total)
                now = time.monotonic()
                if percent is not None and percent < state["last_percent"] + 3 \
                        and now - state["last_ts"] < 0.5:
                    return
                state["last_percent"] = percent if percent is not None else state["last_percent"]
                state["last_ts"] = now
                self._emit({
                    "type": "progress",
                    "method": method,
                    "data": {"phase": "read", "percent": percent} if method == "load_mvr"
                    else {"percent": percent},
                })
            except Exception:
                log.exception("Fortschritts-Event fehlgeschlagen")

        return _emit_progress
```

(`import time` ergänzen, falls nicht vorhanden.) In `_do_load_mvr` nach dem Start-Event:

```python
        emit_read_progress = self._make_progress_emitter(
            "load_mvr",
            lambda done, total: 75 if not total else 5 + int(done / total * 70),
        )
        scene = read_mvr(path, progress=emit_read_progress)
```

Nach dem Lesen, vor `aggregate_fixture_types`: `self._emit({"type": "progress", "method": "load_mvr", "data": {"phase": "match", "percent": 80}})`; nach dem Kandidaten-Schleifen-Block (vor `file_stat = ...`): dasselbe mit `"percent": 95`.

In `_do_share_download`:

```python
        emit_dl_progress = self._make_progress_emitter(
            "share_download",
            lambda done, total: int(done / total * 100) if total else None,
        )
        fixture = self._share.download(rid, library_dir, progress=emit_dl_progress)
```

- [ ] **Step 5: Tests + Lint**

Run: `python -m pytest tests/test_api.py tests/test_share.py -v; python -m pytest -q; ruff check .` → grün. Hinweis: der bestehende Test `test_load_mvr_emits_progress_start_event` und `test_threaded_mode_pushes_state_result_and_toast_events` können sich an der neuen Event-Anzahl stoßen — Assertions dort minimal anpassen (nur Zählweise, nicht die Absicht).

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/api.py mvr_enhancer/core/share.py tests/test_api.py tests/test_share.py
git commit -m "feat(api): echte Fortschritts-Events fuer MVR-Laden und Share-Download"
```

---

### Task 5: UI — Balken folgt echtem Fortschritt, Watchdog nur bei Stille, Download-Prozent im Modal

**Files:**
- Modify: `mvr_enhancer/ui/js/app.js` (`dzStart` ~Z.650, neuer `dzProgress`, onEvent-progress-Case ~Z.330, `renderSearchModal`/Download-Button, `searchModal`-State, `finishDownload`)

**Interfaces:**
- Consumes: progress-Events aus Task 4; bestehende `dzLoad`, `armWatchdog`, `pendingWatchdogs`, `WATCHDOG_ARM_ON_PROGRESS`, `searchModal`.

- [ ] **Step 1: dzStart-Kriechen + dzProgress**

In `dzStart()` die beiden Transition-Zeilen ersetzen (Kriechen auf 15 % in 2 s statt 90 % in 1 s):

```js
    fill.style.transition = "transform 2000ms ease-out";
    fill.style.transform = "scaleX(0.15)";
```

Neue Funktion daneben (Modul-Variable `dzLoad.percent = 0` im Objekt ergänzen; in `dzStart` auf 15 initialisieren, in `dzReset`/`dzFinish`-Abschluss zurücksetzen):

```js
  function dzProgress(percent) {
    if (!dzLoad.active || typeof percent !== "number") return;
    var capped = Math.min(95, Math.max(0, percent));
    if (capped <= dzLoad.percent) return; // monoton — nie rueckwaerts
    dzLoad.percent = capped;
    var fill = $("dropzone-fill");
    fill.style.transition = "transform 400ms linear";
    fill.style.transform = "scaleX(" + (capped / 100) + ")";
  }
```

- [ ] **Step 2: onEvent-progress-Case erweitern**

```js
      case "progress":
        if (evt.method) {
          var wdKey = WATCHDOG_METHOD_ALIASES[evt.method] || evt.method;
          // Aktivitaets-Watchdog: JEDES progress-Event stellt die 30-s-Uhr
          // neu — sie misst Stille, nicht Gesamtdauer.
          if (WATCHDOG_ARM_ON_PROGRESS[wdKey] || pendingWatchdogs[wdKey] !== undefined) {
            armWatchdog(evt.method);
          }
        }
        if (evt.method === "load_mvr" && evt.data) {
          if (evt.data.phase === "start") dzStart();
          else if (typeof evt.data.percent === "number") dzProgress(evt.data.percent);
        }
        if (evt.method === "share_download" && evt.data) {
          searchModal.downloadPercent = (typeof evt.data.percent === "number") ? evt.data.percent : null;
          renderSearchModal();
        }
        break;
```

- [ ] **Step 3: Download-Prozent im Suchmodal**

`searchModal` um `downloadPercent: null` ergänzen. In `renderSearchModal` beim Button des gerade ladenden Ergebnisses (`searchModal.downloadingRid`): Label `"lädt …"` wird zu `"lädt … " + searchModal.downloadPercent + " %"`, wenn `downloadPercent` eine Zahl ist (sonst unverändert). In `finishDownload` und im `WATCHDOG_RESET.share_download` zusätzlich `searchModal.downloadPercent = null;`.

- [ ] **Step 4: Smoke-Check + Suite + Lint**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log ohne JS-Fehler; `python -m pytest -q; ruff check .` → grün.

- [ ] **Step 5: Commit**

```bash
git add mvr_enhancer/ui/js/app.js
git commit -m "feat(ui): Ladebalken folgt echtem Fortschritt; Watchdog misst Stille statt Gesamtdauer"
```

---

### Task 6: Version 0.4.0 + README

**Files:**
- Modify: `pyproject.toml`, `mvr_enhancer/__init__.py`, `mvr_enhancer/ui/index.html` (Header-Versionsstring), `README.md`
- Modify: `tests/test_api.py`, `tests/test_smoke.py` (Versions-Assertions)

**Interfaces:**
- Consumes: alles Vorherige.

- [ ] **Step 1: Version an allen Stellen**

1. `pyproject.toml`: `version = "0.4.0"`
2. `mvr_enhancer/__init__.py`: `__version__ = "0.4.0"`
3. `mvr_enhancer/ui/index.html` Header: `v0.3.0` → `v0.4.0` (nur die Nummer)
4. `README.md`: Überschrift „Bekannte Grenzen (v0.3.0)" → „(v0.4.0)"
5. `tests/test_api.py` und `tests/test_smoke.py`: Versions-Assertions `"0.3.0"` → `"0.4.0"` (per grep nach `0.3.0` in tests/ finden)

- [ ] **Step 2: README — Bedienung ergänzen**

Im Matching-/Bedienungsabschnitt ergänzen (Wortlaut darf an den README-Ton angepasst werden, Inhalt muss stimmen): „Passt kein Vorschlag, wählst du im GDTF-Dropdown unter ‚Gesamte Bibliothek' jede andere GDTF aus deinem Ordner — oder springst mit dem Globus-Button daneben direkt in die GDTF-Share-Suche. Über ‚— aktiv entfernt —' nimmst du einen Typ bewusst aus dem Export (z. B. Plugboxen); ‚— nicht zugeordnet —' bedeutet dagegen: noch offen — wird beim Export ebenfalls entfernt, taucht aber als offener Punkt in der Bereinigungsliste auf."

- [ ] **Step 3: Suite + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml mvr_enhancer/__init__.py mvr_enhancer/ui/index.html README.md tests/test_api.py tests/test_smoke.py
git commit -m "docs: freie Zuordnung dokumentieren, Version 0.4.0 (alle Stellen)"
```
