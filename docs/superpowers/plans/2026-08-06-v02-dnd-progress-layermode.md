# MVR Enhancer v0.2 Implementation Plan (Drag&Drop, Ladebalken, Export-Layer-Modus)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drag&Drop auf die Dropzone funktioniert, die Dropzone wird beim Laden zum ≥1-s-Ladebalken, und ein persistierter Switch wählt zwischen Single-Layer- und Per-Layer-Export.

**Architecture:** Drei weitgehend unabhängige Stränge auf der bestehenden pywebview-App: (1) ein Python-seitiger DOM-Drop-Listener (pywebview reicht Dateipfade nur dann durch), (2) ein reines Frontend-Feature (CSS-Füllbalken + Timing in app.js, getriggert von einem neuen `progress`-Event), (3) Layer-Provenienz im Reader + neuer `layer_mode` durch Enricher/Settings/Api/UI.

**Tech Stack:** Python 3.11+, pywebview (EdgeChromium/WebView2), Vanilla JS/CSS, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-06-v02-dnd-progress-layermode-design.md`

## Global Constraints

- UI-Sprache Deutsch, informelles „du"; ASCII-Umlaut-Escapes nur in Python-Strings nötig, HTML nutzt Entities wie bisher.
- Blauton des Ladebalkens: `var(--blue-600)` (#1e7cc4), Füllung mit reduzierter Deckkraft `rgba(30, 124, 196, 0.35)`.
- Ladebalken-Mindestlaufzeit: **1000 ms**, Füllung 0→90 % in 1 s, Abschluss 90→100 % in ~150 ms.
- Export-Layer-Name unverändert: `MVR Enhancer Export` (`_LAYER_NAME` in enricher.py).
- `layer_mode`-Werte exakt: `"single"` | `"per_layer"`; jeder andere Wert wird zu `"single"` normalisiert. Default `"single"`.
- Per-Layer-3D-Grouping: `name="3D"`, `uuid = uuid5(_NS, f"group_3D_{original_layer_uuid}")`; Layer-uuid-Fallback `uuid5(_NS, f"layer_orig_{index}")`, Name-Fallback `f"Layer {index + 1}"`, Matrix-Fallback `_IDENTITY_MATRIX`. `_NS` ist das bestehende Namespace-UUID in enricher.py.
- XML-Reihenfolge Per-Layer: zuerst Layer „MVR Enhancer Export", danach Original-Layer in Originalreihenfolge; im Export-Layer gibt es im Per-Layer-Modus KEIN „3D"-GroupObject.
- Alle Dateidialog-Beschreibungen: nur `[\w ]` (kein Bindestrich — pywebview-Regex, siehe v0.1-Bug 1).
- Die App NIE im Vordergrund starten (`webview.start()` blockiert); für Smoke-Checks `Start-Process` + `Stop-Process` nach Timeout.
- Tests: pytest; Api-Tests mit `Api(sync=True)`; `ruff check .` muss sauber bleiben.
- Version am Ende: `0.2.0` in pyproject.toml.

---

### Task 1: Reader — Layer-Provenienz (`MvrLayerInfo`)

**Files:**
- Modify: `mvr_enhancer/core/mvr_reader.py` (Dataclasses ~Z.90–113, Layer-Schleife ~Z.314–321)
- Modify: `tests/builders.py` (build_mvr um `scene_objects` + `layer_matrix` erweitern)
- Test: `tests/test_mvr_reader.py`

**Interfaces:**
- Consumes: bestehende `MvrScene`, `_collect_elements`, `read_mvr`.
- Produces: `MvrLayerInfo(uuid: str, name: str, matrix_text: str | None, non_fixture_elements: list[ET.Element])`; `MvrScene.layers: list[MvrLayerInfo]` (Default `[]`). Rohwerte, keine Fallbacks (die macht Task 2 im Enricher). `tests/builders.build_mvr(..., scene_objects=[{"name": ..., "uuid": ..., "layer": ...}], layer_matrix={"LayerName": "{...}{...}{...}{...}"})`.

- [ ] **Step 1: builders.py erweitern**

In `build_mvr` Signatur ergänzen: `scene_objects: list[dict] | None = None, layer_matrix: dict[str, str] | None = None`. Nach `embedded = embedded or {}`: `scene_objects = scene_objects or []` und `layer_matrix = layer_matrix or {}`. In `_child_list_for_layer` direkt nach dem Anlegen von `layer_el` (vor dem ChildList-SubElement):

```python
            if layer_name in layer_matrix:
                layer_matrix_el = ET.SubElement(layer_el, "Matrix")
                layer_matrix_el.text = layer_matrix[layer_name]
```

Achtung: `<Matrix>` muss VOR `<ChildList>` eingefügt werden — den bestehenden `layer_child_lists[layer_name] = ET.SubElement(...)`-Aufruf entsprechend danach lassen. Nach der Fixture-Schleife (vor dem AUXData-Block):

```python
    for scene_object in scene_objects:
        child_list_el = _child_list_for_layer(scene_object.get("layer", "Layer 1"))
        ET.SubElement(
            child_list_el,
            "SceneObject",
            {
                "name": scene_object.get("name", "Object"),
                "uuid": scene_object.get("uuid", str(uuid.uuid4())),
            },
        )
```

Docstring von `build_mvr` um beide Parameter ergänzen (ein Satz je Parameter).

- [ ] **Step 2: Failing Tests schreiben**

In `tests/test_mvr_reader.py` (bestehende Imports nutzen; `build_mvr` kommt aus `tests.builders`):

```python
def test_layers_provenance_collects_per_layer(tmp_path):
    mvr = build_mvr(
        tmp_path / "prov.mvr",
        fixtures=[
            {"name": "Spot 1", "layer": "Rig A", "address": 1},
            {"name": "Spot 2", "layer": "Rig B", "address": 17},
        ],
        scene_objects=[
            {"name": "Truss A", "layer": "Rig A"},
            {"name": "Deko B1", "layer": "Rig B"},
            {"name": "Deko B2", "layer": "Rig B"},
        ],
        layer_matrix={"Rig A": "{1,0,0}{0,1,0}{0,0,1}{5,5,0}"},
    )
    scene = read_mvr(str(mvr))

    assert [layer.name for layer in scene.layers] == ["Rig A", "Rig B"]
    assert all(layer.uuid for layer in scene.layers)
    assert scene.layers[0].matrix_text == "{1,0,0}{0,1,0}{0,0,1}{5,5,0}"
    assert scene.layers[1].matrix_text is None
    assert [el.get("name") for el in scene.layers[0].non_fixture_elements] == ["Truss A"]
    assert [el.get("name") for el in scene.layers[1].non_fixture_elements] == ["Deko B1", "Deko B2"]


def test_layers_provenance_shares_element_objects_with_flat_list(tmp_path):
    mvr = build_mvr(
        tmp_path / "identity.mvr",
        fixtures=[{"name": "Spot 1", "layer": "Rig A", "address": 1}],
        scene_objects=[
            {"name": "Truss A", "layer": "Rig A"},
            {"name": "Deko B", "layer": "Rig B"},
        ],
    )
    scene = read_mvr(str(mvr))

    from_layers = [el for layer in scene.layers for el in layer.non_fixture_elements]
    assert len(from_layers) == len(scene.non_fixture_elements) == 2
    for a, b in zip(from_layers, scene.non_fixture_elements):
        assert a is b


def test_layers_default_empty_on_invalid_mvr(tmp_path):
    bad = tmp_path / "bad.mvr"
    bad.write_bytes(b"not a zip")
    scene = read_mvr(str(bad))
    assert scene.layers == []
```

- [ ] **Step 3: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_mvr_reader.py -k layers_provenance -v`
Expected: FAIL (`build_mvr() got an unexpected keyword argument 'scene_objects'` bzw. `MvrScene has no attribute 'layers'`)

- [ ] **Step 4: Reader implementieren**

In `mvr_reader.py` — Dataclass vor `MvrScene` einfügen:

```python
@dataclass
class MvrLayerInfo:
    """Provenienz eines Original-Layers: Rohwerte, ohne Fallbacks.

    Fallbacks fuer fehlende uuid/name/matrix wendet erst der Enricher beim
    Bauen des Per-Layer-Exports an (das uuid5-Namespace lebt dort).
    """

    uuid: str
    name: str
    matrix_text: str | None
    non_fixture_elements: list[ET.Element] = field(default_factory=list)
```

`MvrScene` ergänzen: `layers: list[MvrLayerInfo] = field(default_factory=list)`.

Die Layer-Schleife in `read_mvr` ersetzen:

```python
    for layer in layers_el.findall("Layer"):
        layer_non_fixtures: list[ET.Element] = []
        _collect_elements(layer, scene.fixtures, layer_non_fixtures)
        scene.non_fixture_elements.extend(layer_non_fixtures)
        layer_matrix_el = layer.find("Matrix")
        matrix_text = None
        if layer_matrix_el is not None and layer_matrix_el.text:
            matrix_text = layer_matrix_el.text
        scene.layers.append(MvrLayerInfo(
            uuid=layer.get("uuid", ""),
            name=layer.get("name", ""),
            matrix_text=matrix_text,
            non_fixture_elements=layer_non_fixtures,
        ))
```

Wichtig: `layer_non_fixtures` wird für BEIDE Sichten verwendet (dieselben Element-Objekte, keine Kopien).

- [ ] **Step 5: Tests laufen lassen — müssen bestehen**

Run: `python -m pytest tests/test_mvr_reader.py tests/test_builders.py -v`
Expected: PASS (alle, auch die Bestandstests — die flache Liste ist unverändert)

- [ ] **Step 6: Gesamtsuite + Lint**

Run: `python -m pytest -q; ruff check .`
Expected: alles grün

- [ ] **Step 7: Commit**

```bash
git add mvr_enhancer/core/mvr_reader.py tests/builders.py tests/test_mvr_reader.py
git commit -m "feat(reader): Layer-Provenienz als MvrLayerInfo erfassen"
```

---

### Task 2: Enricher — `layer_mode` („single" | „per_layer")

**Files:**
- Modify: `mvr_enhancer/core/enricher.py` (`_reorganize_layers` ~Z.187–255, `enrich_mvr` ~Z.325–332 und Aufruf ~Z.448)
- Test: `tests/test_enricher.py`

**Interfaces:**
- Consumes: `MvrScene.layers: list[MvrLayerInfo]` (Task 1), bestehende `_NS`, `_LAYER_NAME`, `_IDENTITY_MATRIX`.
- Produces: `enrich_mvr(..., group_by_position: bool = True, layer_mode: str = "single")`; `_reorganize_layers(scene, kept_fixtures, group_by_position, layer_mode)`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_enricher.py` (an bestehende Helper/Imports anlehnen — dort existieren bereits Tests, die `enrich_mvr` mit `build_mvr`-Szenen aufrufen und den Export per `zipfile`/`ET.fromstring` inspizieren; denselben Aufbau verwenden). Kern-Assertions:

```python
def _export_root(result):
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        return ET.fromstring(zf.read("GeneralSceneDescription.xml"))


def test_per_layer_keeps_original_layers_with_3d_grouping(tmp_path):
    # Szene: 1 zugeordnete Fixture in "Rig A", SceneObjects in "Rig A" und
    # "Rig B", Layer "Leer" ohne Nicht-Fixture-Elemente (nur eine entfernte
    # Fixture), Matrix nur auf "Rig A".
    mvr = build_mvr(
        tmp_path / "src.mvr",
        fixtures=[
            {"name": "Spot 1", "layer": "Rig A", "address": 1},
            {"name": "Plugbox", "layer": "Leer", "address": 100},
        ],
        scene_objects=[
            {"name": "Truss A", "layer": "Rig A"},
            {"name": "Deko B", "layer": "Rig B"},
        ],
        layer_matrix={"Rig A": "{1,0,0}{0,1,0}{0,0,1}{5,5,0}"},
    )
    scene = read_mvr(str(mvr))
    types = aggregate_fixture_types(scene)
    assignments = {...}  # wie in den Bestandstests: "Spot 1" zugeordnet, "Plugbox" removed
    result = enrich_mvr(scene, types, assignments, str(lib_dir), library,
                        group_by_position=False, layer_mode="per_layer")

    root = _export_root(result)
    layer_els = root.findall("./Scene/Layers/Layer")
    assert [layer.get("name") for layer in layer_els] == ["MVR Enhancer Export", "Rig A", "Rig B"]

    export_layer = layer_els[0]
    # KEIN 3D-Grouping im Export-Layer im per_layer-Modus:
    assert export_layer.find("./ChildList/GroupObject[@name='3D']") is None
    assert len(export_layer.findall("./ChildList/Fixture")) == 1

    rig_a = layer_els[1]
    src_scene = read_mvr(str(mvr))
    assert rig_a.get("uuid") == src_scene.layers[0].uuid          # Original-uuid
    assert rig_a.find("Matrix").text == "{1,0,0}{0,1,0}{0,0,1}{5,5,0}"
    groups = rig_a.findall("./ChildList/GroupObject")
    assert len(groups) == 1 and groups[0].get("name") == "3D"
    import uuid as uuid_mod
    from mvr_enhancer.core.enricher import _NS
    assert groups[0].get("uuid") == str(uuid_mod.uuid5(_NS, f"group_3D_{rig_a.get('uuid')}"))
    assert [el.get("name") for el in groups[0].findall("./ChildList/SceneObject")] == ["Truss A"]

    rig_b = layer_els[2]
    assert rig_b.find("Matrix").text == _IDENTITY_MATRIX          # Fallback
    # "Leer" fehlt: keine Nicht-Fixture-Elemente.


def test_per_layer_grouping_by_position_still_works(tmp_path):
    # group_by_position=True + layer_mode="per_layer": Positions-Gruppen im
    # Export-Layer vorhanden, Original-Layer zusaetzlich.
    ...


def test_unknown_layer_mode_falls_back_to_single(tmp_path):
    # layer_mode="quatsch" erzeugt exakt denselben Baum wie layer_mode="single"
    # (ein Layer, 3D-Gruppe im Export-Layer).
    ...


def test_per_layer_without_layer_infos_falls_back_to_single_3d_group(tmp_path):
    # Defensive: MvrScene mit non_fixture_elements, aber leerer layers-Liste
    # (synthetisch konstruiert) -> Elemente landen in der 3D-Gruppe des
    # Export-Layers statt verloren zu gehen.
    ...
```

Die `...`-Tests analog zum ersten ausformulieren (die Assertions stehen im jeweiligen Kommentar); `assignments`/`lib_dir`/`library` exakt wie in den vorhandenen `enrich_mvr`-Tests der Datei aufbauen.

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_enricher.py -k "per_layer or unknown_layer_mode" -v`
Expected: FAIL (`enrich_mvr() got an unexpected keyword argument 'layer_mode'`)

- [ ] **Step 3: Enricher implementieren**

`enrich_mvr`-Signatur: nach `group_by_position: bool = True` den Parameter `layer_mode: str = "single"` ergänzen; Docstring um zwei Sätze zu den Modi erweitern. Direkt am Funktionsanfang normalisieren:

```python
    if layer_mode != "per_layer":
        layer_mode = "single"
```

Aufruf anpassen: `root, position_group_count = _reorganize_layers(scene, kept_fixtures, group_by_position, layer_mode)`.

`_reorganize_layers(scene, kept_fixtures, group_by_position, layer_mode)`: Der bestehende Block `if scene.non_fixture_elements:` (3D-Gruppe im Export-Layer) wird ersetzt durch:

```python
    if layer_mode == "per_layer" and scene.layers:
        for index, layer_info in enumerate(scene.layers):
            if not layer_info.non_fixture_elements:
                continue
            orig_uuid = layer_info.uuid or str(uuid.uuid5(_NS, f"layer_orig_{index}"))
            orig_layer = ET.SubElement(layers_el, "Layer")
            orig_layer.set("uuid", orig_uuid)
            orig_layer.set("name", layer_info.name or f"Layer {index + 1}")
            orig_matrix = ET.SubElement(orig_layer, "Matrix")
            orig_matrix.text = layer_info.matrix_text or _IDENTITY_MATRIX
            orig_cl = ET.SubElement(orig_layer, "ChildList")
            group_3d = ET.SubElement(orig_cl, "GroupObject")
            group_3d.set("uuid", str(uuid.uuid5(_NS, f"group_3D_{orig_uuid}")))
            group_3d.set("name", "3D")
            group_3d_matrix = ET.SubElement(group_3d, "Matrix")
            group_3d_matrix.text = _IDENTITY_MATRIX
            group_3d_cl = ET.SubElement(group_3d, "ChildList")
            for el in layer_info.non_fixture_elements:
                group_3d_cl.append(el)
    elif scene.non_fixture_elements:
        # single-Modus — bestehender Block unveraendert (3D-Gruppe im
        # Export-Layer). Greift auch als Fallback, wenn eine synthetische
        # Szene keine Layer-Provenienz traegt (layers == []).
        ...bestehenden Block hier belassen...
```

Docstring von `_reorganize_layers` um den Per-Layer-Absatz ergänzen (Original-Layer erhalten, je ein 3D-Grouping, leere Original-Layer entfallen).

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `python -m pytest tests/test_enricher.py -v`
Expected: PASS (auch alle Bestandstests — Default `"single"` ändert nichts)

- [ ] **Step 5: Gesamtsuite + Lint**

Run: `python -m pytest -q; ruff check .`
Expected: grün

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/core/enricher.py tests/test_enricher.py
git commit -m "feat(enricher): Per-Layer-Exportmodus mit Original-Layern und 3D-Grouping"
```

---

### Task 3: Settings — `export_layer_mode` persistieren

**Files:**
- Modify: `mvr_enhancer/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `Settings.export_layer_mode: str = "single"` — nach `load()` garantiert einer der Werte `"single"`/`"per_layer"`; in `save()` enthalten.

- [ ] **Step 1: Failing Tests schreiben**

```python
def test_export_layer_mode_roundtrip(tmp_path):
    s = Settings.load(str(tmp_path))
    assert s.export_layer_mode == "single"
    s.export_layer_mode = "per_layer"
    s.save()
    assert Settings.load(str(tmp_path)).export_layer_mode == "per_layer"


def test_export_layer_mode_invalid_value_normalized(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"export_layer_mode": "banane"}', encoding="utf-8"
    )
    assert Settings.load(str(tmp_path)).export_layer_mode == "single"


def test_export_layer_mode_non_string_normalized(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"export_layer_mode": 7}', encoding="utf-8"
    )
    assert Settings.load(str(tmp_path)).export_layer_mode == "single"
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_settings.py -k export_layer_mode -v`
Expected: FAIL (`'Settings' object has no attribute 'export_layer_mode'`)

- [ ] **Step 3: Implementieren**

Dataclass-Feld nach `group_by_position`: `export_layer_mode: str = "single"`. In `load()` nach `settings = cls(**kwargs)`:

```python
        if settings.export_layer_mode not in ("single", "per_layer"):
            settings.export_layer_mode = "single"
```

In `save()`-Payload nach `"group_by_position"`: `"export_layer_mode": self.export_layer_mode,`.

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `python -m pytest tests/test_settings.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add mvr_enhancer/settings.py tests/test_settings.py
git commit -m "feat(settings): export_layer_mode persistieren"
```

---

### Task 4: Api — `set_layer_mode`, State, Export-Durchreichung, Lade-Progress-Event

**Files:**
- Modify: `mvr_enhancer/api.py` (`__init__` ~Z.131, `_do_startup`-Reload-Stelle ~Z.466, `get_state`-Payload, `set_grouping`-Nachbarschaft ~Z.578, `_do_load_mvr` ~Z.395, `run_export`-Snapshots ~Z.835–897)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Settings.export_layer_mode` (Task 3), `enrich_mvr(..., layer_mode=...)` (Task 2).
- Produces: `Api.set_layer_mode(mode: str) -> dict`; `get_state()["data"]["layer_mode"]: str`; Event `{"type": "progress", "method": "load_mvr", "data": {"phase": "start"}}` zu Beginn jedes Ladevorgangs. (Das UI-Rendering dazu bauen Tasks 6/7.)

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_api.py`, im Stil der Bestandstests (`Api(sync=True)`, Settings via `base_dir=tmp_path`; exakte Konstruktion aus den vorhandenen Tests übernehmen):

```python
def test_layer_mode_in_state_and_setter(api):
    assert api.get_state()["data"]["layer_mode"] == "single"
    result = api.set_layer_mode("per_layer")
    assert result["ok"] and result["data"]["layer_mode"] == "per_layer"
    # persistiert:
    assert api._settings.export_layer_mode == "per_layer"


def test_set_layer_mode_rejects_unknown_value(api):
    result = api.set_layer_mode("banane")
    assert not result["ok"]
    assert api.get_state()["data"]["layer_mode"] == "single"


def test_load_mvr_emits_progress_start_event(api, tmp_path):
    mvr = build_mvr(tmp_path / "a.mvr", fixtures=[{"name": "Spot 1", "address": 1}])
    api.load_mvr(str(mvr))
    progress = [e for e in api.events
                if e.get("type") == "progress" and e.get("method") == "load_mvr"]
    assert progress and progress[0]["data"]["phase"] == "start"


def test_run_export_passes_layer_mode(api, tmp_path, monkeypatch):
    # Wie der bestehende run_export-Test aufgebaut; zusaetzlich:
    api.set_layer_mode("per_layer")
    captured = {}
    import mvr_enhancer.api as api_mod
    real = api_mod.enrich_mvr
    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)
    monkeypatch.setattr(api_mod, "enrich_mvr", spy)
    ...run_export wie im Bestandstest ausloesen...
    assert captured.get("layer_mode") == "per_layer"
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_api.py -k "layer_mode or progress_start" -v`
Expected: FAIL (`'Api' object has no attribute 'set_layer_mode'` / KeyError `layer_mode`)

- [ ] **Step 3: Implementieren**

1. `__init__` nach `self._grouping = ...`: `self._layer_mode = self._settings.export_layer_mode` (Settings.load hat bereits normalisiert).
2. An der Reload-Stelle ~Z.466 (wo `self._grouping = self._settings.group_by_position` erneut gesetzt wird) analog: `self._layer_mode = self._settings.export_layer_mode`.
3. `get_state`: im data-Dict direkt neben `"grouping"` den Schlüssel `"layer_mode": self._layer_mode` ergänzen (innerhalb des bestehenden Locks).
4. Neue Methode direkt nach `set_grouping`:

```python
    def set_layer_mode(self, mode: str) -> dict:
        try:
            if mode not in ("single", "per_layer"):
                return {"ok": False, "error": "Unbekannter Export-Modus."}
            with self._lock:
                self._layer_mode = mode
                self._settings.export_layer_mode = mode
                self._settings.save()
            return {"ok": True, "data": self.get_state()["data"]}
        except Exception as e:
            log.exception("set_layer_mode fehlgeschlagen")
            return {"ok": False, "error": f"Export-Modus konnte nicht gesetzt werden: {e}"}
```

5. `_do_load_mvr`: als ALLERERSTE Zeile (vor dem isfile-Check):

```python
        self._emit({"type": "progress", "method": "load_mvr", "data": {"phase": "start"}})
```

6. `run_export`: im Snapshot-Block `layer_mode_snapshot = self._layer_mode` ergänzen; im `enrich_mvr(...)`-Aufruf `layer_mode=layer_mode_snapshot` anhängen.

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `python -m pytest tests/test_api.py -v` → PASS

- [ ] **Step 5: Gesamtsuite + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/api.py tests/test_api.py
git commit -m "feat(api): layer_mode-State/-Setter, Export-Durchreichung, Lade-Progress-Event"
```

---

### Task 5: Drag&Drop — Python-DOM-Listener + Api-Handler

**Files:**
- Modify: `mvr_enhancer/api.py` (neue Methode `on_dropzone_drop`, bei den Datei-Methoden nahe `load_mvr`)
- Modify: `mvr_enhancer/main.py` (`run()`, nach `api.set_window(window)`)
- Modify: `mvr_enhancer/ui/js/app.js` (Drop-Handler ~Z.1010–1020 entschlacken)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Api.load_mvr(path)`, `Api._emit`.
- Produces: `Api.on_dropzone_drop(event: dict) -> None` — von pywebview (fremder Thread) aufgerufen; wirft nie.

**Hintergrund (für den Implementer):** pywebview reicht native Dateipfade nur durch, wenn ein Python-seitiger DOM-Drop-Listener registriert ist (`webview/platforms/edgechromium.py` verwirft `FilesDropped` bei `_dnd_state['num_listeners'] == 0`; nur `Element.on('drop', …)` erhöht den Zähler). `pywebviewFullPath` wird dabei ausschließlich in die an Python serialisierte Event-Kopie injiziert (`webview/util.py`), nie ins JS-`File`-Objekt — der bisherige JS-Zugriff darauf konnte nie funktionieren.

- [ ] **Step 1: Failing Tests schreiben**

```python
def _drop_event(files):
    return {"dataTransfer": {"files": files}}


def test_dropzone_drop_loads_first_mvr(api, tmp_path):
    mvr = build_mvr(tmp_path / "d.mvr", fixtures=[{"name": "Spot 1", "address": 1}])
    api.on_dropzone_drop(_drop_event([
        {"name": "readme.txt", "pywebviewFullPath": str(tmp_path / "readme.txt")},
        {"name": "d.mvr", "pywebviewFullPath": str(mvr)},
    ]))
    assert api.get_state()["data"]["mvr_loaded"] is True


def test_dropzone_drop_without_mvr_shows_info_toast(api):
    api.on_dropzone_drop(_drop_event([{"name": "bild.png", "pywebviewFullPath": "C:/x/bild.png"}]))
    toasts = [e for e in api.events if e.get("type") == "toast"]
    assert toasts and toasts[-1]["level"] == "info"
    assert toasts[-1]["method"] == "dropzone"
    assert api.get_state()["data"]["mvr_loaded"] is False


def test_dropzone_drop_ignores_file_without_full_path(api):
    # WebView2 liefert ohne registrierten Listener/bei Sonderfaellen kein
    # pywebviewFullPath — dann Toast statt Absturz.
    api.on_dropzone_drop(_drop_event([{"name": "d.mvr"}]))
    toasts = [e for e in api.events if e.get("type") == "toast"]
    assert toasts and toasts[-1]["level"] == "info"


def test_dropzone_drop_malformed_event_never_raises(api):
    api.on_dropzone_drop(None)
    api.on_dropzone_drop({})
    api.on_dropzone_drop({"dataTransfer": {"files": "kaputt"}})
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `python -m pytest tests/test_api.py -k dropzone -v`
Expected: FAIL (`'Api' object has no attribute 'on_dropzone_drop'`)

- [ ] **Step 3: Api-Handler implementieren**

Nahe `load_mvr` in api.py:

```python
    def on_dropzone_drop(self, event) -> None:
        """pywebview-DOM-Drop auf #dropzone (laeuft in einem pywebview-Thread).

        Der einzige Weg, an den nativen Dateipfad zu kommen: pywebview
        injiziert ``pywebviewFullPath`` nur in die an Python serialisierte
        Event-Kopie, nie ins JS-File-Objekt. Wirft nie — Fehler enden als
        Log + Toast, die App bleibt per Dialog bedienbar.
        """
        try:
            data_transfer = event.get("dataTransfer") if isinstance(event, dict) else None
            files = data_transfer.get("files") if isinstance(data_transfer, dict) else None
            if isinstance(files, list):
                for dropped in files:
                    if not isinstance(dropped, dict):
                        continue
                    path = dropped.get("pywebviewFullPath") or ""
                    name = dropped.get("name") or path
                    if path and str(name).lower().endswith(".mvr"):
                        self.load_mvr(path)
                        return
            self._emit({
                "type": "toast",
                "method": "dropzone",
                "level": "info",
                "message": "Bitte eine .mvr-Datei ablegen.",
            })
        except Exception:
            log.exception("Drop-Verarbeitung fehlgeschlagen")
```

(`method: "dropzone"` verhindert, dass der Info-Toast per `clearAllWatchdogs` fremde Watchdogs auflöst — siehe `handleToastEvent` in app.js.)

- [ ] **Step 4: main.py — Listener registrieren**

In `run()` nach `api.set_window(window)`:

```python
    def _register_dropzone_dnd() -> None:
        # Erst nach dem Laden der Seite existiert #dropzone. Ohne diesen
        # Python-seitigen Listener reicht pywebview keine nativen Dateipfade
        # durch (siehe on_dropzone_drop) — schlaegt die Registrierung fehl,
        # bleibt die App ueber den Datei-Dialog voll bedienbar.
        try:
            element = window.dom.get_element("#dropzone")
            if element is None:
                log.warning("#dropzone nicht gefunden — Drag&Drop deaktiviert")
                return
            element.on("drop", api.on_dropzone_drop)
            log.info("Drag&Drop-Listener registriert")
        except Exception:
            log.exception("Drag&Drop-Registrierung fehlgeschlagen")

    window.events.loaded += _register_dropzone_dnd
```

- [ ] **Step 5: app.js — Drop-Handler entschlacken**

Den bestehenden `drop`-Listener (Z.1010–1020) ersetzen durch:

```js
    dropzone.addEventListener("drop", function (e) {
      // Nur Optik: das Laden uebernimmt der Python-seitige DOM-Listener
      // (main.py) — pywebview reicht Dateipfade ausschliesslich an Python
      // durch, ein JS-seitiger pywebviewFullPath-Zugriff ist prinzipbedingt
      // immer leer.
      e.preventDefault();
      dropzone.classList.remove("drag-over");
    });
```

`dragover`/`dragleave` bleiben unverändert.

- [ ] **Step 6: Tests + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 7: Smoke-Check (App darf nie im Vordergrund laufen!)**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 8; Stop-Process -Id $p.Id -Force
```

Danach im Log (`%APPDATA%/MVR Enhancer/mvr-enhancer.log`) prüfen: Zeile „Drag&Drop-Listener registriert" vorhanden, keine Exception.

- [ ] **Step 8: Commit**

```bash
git add mvr_enhancer/api.py mvr_enhancer/main.py mvr_enhancer/ui/js/app.js tests/test_api.py
git commit -m "fix(dnd): Python-seitigen DOM-Drop-Listener registrieren — Drag&Drop laedt MVRs"
```

---

### Task 6: UI — Export-Modus-Switch (Segmented Control)

**Files:**
- Modify: `mvr_enhancer/ui/index.html` (Sources-Bar, nach dem `chk-gruppieren`-Label ~Z.151, vor `sources-bar-right`)
- Modify: `mvr_enhancer/ui/css/app.css` (bei den Sources-Bar-/Button-Styles)
- Modify: `mvr_enhancer/ui/js/app.js` (`renderSection2` ~Z.682, Event-Bindings bei `chk-gruppieren` ~Z.1047)

**Interfaces:**
- Consumes: `state.layer_mode` (Task 4), `callApi("set_layer_mode", mode)`.
- Produces: sichtbarer Zwei-Segment-Schalter „Single Layer | Per Layer" mit Label „Export:".

- [ ] **Step 1: Markup einfügen**

In index.html direkt nach dem schließenden `</label>` der Gruppieren-Checkbox (vor `<div class="sources-bar-right">`):

```html
                  <span class="v-sep"></span>
                  <div class="seg" id="seg-layer-mode" role="group" aria-label="Export-Modus">
                    <span class="seg-label">Export:</span>
                    <button id="seg-single" type="button" class="seg-btn seg-btn-left" data-mode="single">Single Layer</button>
                    <button id="seg-per-layer" type="button" class="seg-btn seg-btn-right" data-mode="per_layer">Per Layer</button>
                  </div>
```

- [ ] **Step 2: CSS ergänzen**

In app.css bei den Sources-Bar-Styles:

```css
.seg { display: flex; align-items: center; gap: 10px; }
.seg-label { font-size: 13px; color: var(--text-inverse-muted); }
.seg-btn {
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-inverse-muted);
  background: transparent;
  border: 1px solid var(--border-dark);
  cursor: pointer;
}
.seg-btn-left { border-radius: 8px 0 0 8px; border-right: none; }
.seg-btn-right { border-radius: 0 8px 8px 0; }
.seg-btn:hover { color: var(--white); }
.seg-btn.active {
  background: var(--blue-600);
  border-color: var(--blue-600);
  color: var(--white);
}
.seg-btn:focus-visible { outline: 2px solid var(--blue-300); outline-offset: -1px; }
```

(Werte an die bestehenden `btn-outline btn-sm`-Styles anpassen, falls deren Padding/Radius abweicht — die Nachbarschaft in der Sources-Bar muss optisch bündig sein: gleiche Höhe wie der „Anmelden"-Button.)

- [ ] **Step 3: JS verdrahten**

In `renderSection2` nach `$("chk-gruppieren").checked = !!s.grouping;`:

```js
    var layerMode = s.layer_mode || "single";
    $("seg-single").classList.toggle("active", layerMode === "single");
    $("seg-per-layer").classList.toggle("active", layerMode === "per_layer");
```

Bei den Bindings (nach dem `chk-gruppieren`-Listener):

```js
    $("seg-layer-mode").addEventListener("click", function (e) {
      var btn = e.target.closest(".seg-btn");
      if (btn && btn.dataset.mode) callApi("set_layer_mode", btn.dataset.mode);
    });
```

Zusätzlich muss `layer_mode` im initialen Default-State auftauchen, falls app.js einen lokalen Default-State-Stub pflegt (prüfen: Suche nach `mvr_loaded` im State-Initialisierungsblock; wenn dort ein Default-Objekt existiert, `layer_mode: "single"` ergänzen).

- [ ] **Step 4: Smoke-Check**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log auf JS-Fehler prüfen (keine `evaluate_js`-Exceptions). Danach `python -m pytest -q; ruff check .` → grün.

- [ ] **Step 5: Commit**

```bash
git add mvr_enhancer/ui/index.html mvr_enhancer/ui/css/app.css mvr_enhancer/ui/js/app.js
git commit -m "feat(ui): Export-Modus-Switch Single Layer / Per Layer"
```

---

### Task 7: UI — Dropzone als Ladebalken (≥1 s)

**Files:**
- Modify: `mvr_enhancer/ui/index.html` (Dropzone ~Z.45–49)
- Modify: `mvr_enhancer/ui/css/app.css` (Dropzone-Styles ~Z.281–306)
- Modify: `mvr_enhancer/ui/js/app.js` (onEvent `progress`-Case ~Z.318, `applyState` ~Z.241, `renderSection1` ~Z.632, `WATCHDOG_ARM_ON_PROGRESS` ~Z.132, `WATCHDOG_RESET` ~Z.139, `handleToastEvent` ~Z.329)

**Interfaces:**
- Consumes: `{"type":"progress","method":"load_mvr","data":{"phase":"start"}}` (Task 4).
- Produces: Ladebalken-Verhalten; keine neue API.

- [ ] **Step 1: Markup**

In index.html als ERSTES Kind der Dropzone (vor dem Icon-Span):

```html
                <div id="dropzone" class="dropzone" role="button" tabindex="0">
                  <div id="dropzone-fill" class="dropzone-fill"></div>
                  <span class="icon ic-40 ic-blue300" data-icon="upload"></span>
                  <div id="dropzone-title" class="dropzone-title">MVR-Datei hier ablegen</div>
                  <div id="dropzone-sub" class="dropzone-sub">oder klicken, um eine Datei zu w&auml;hlen &mdash; die 3D-Szene bleibt unangetastet</div>
                </div>
```

(Nur `id`-Attribute auf Titel/Sub ergänzen und den Fill-Div einfügen — Texte unverändert.)

- [ ] **Step 2: CSS**

```css
.dropzone { position: relative; overflow: hidden; }
.dropzone > .icon,
.dropzone-title,
.dropzone-sub { position: relative; z-index: 1; }
.dropzone-fill {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: rgba(30, 124, 196, 0.35); /* --blue-600 @ 35% */
  transform: scaleX(0);
  transform-origin: left center;
  pointer-events: none;
}
.dropzone.loading { cursor: default; }
.dropzone.loading .dropzone-sub { visibility: hidden; }
```

Hinweis: `.dropzone { position: relative; ... }` in die BESTEHENDE `.dropzone`-Regel integrieren (nicht duplizieren); `inset: 0` deckt bei content-box die Padding-Fläche mit ab — gewollt, der Balken füllt die ganze Zone. Der Fortschritt wird über `transform: scaleX()` animiert (per Inline-Style aus JS), nicht über `width` — das rendert ohne Layout-Thrash.

- [ ] **Step 3: JS — Timing-Logik**

Neue Modul-Variablen bei den anderen UI-Flags (`exporting` etc.):

```js
  var dzLoad = { active: false, startTs: 0, finishTimer: null };
  var DZ_MIN_MS = 1000;
  var DZ_TITLE_IDLE = "MVR-Datei hier ablegen";
  var DZ_TITLE_LOADING = "Lade \u2026";
```

Hilfsfunktionen (bei renderSection1 platzieren):

```js
  function dzStart() {
    if (dzLoad.finishTimer) { clearTimeout(dzLoad.finishTimer); dzLoad.finishTimer = null; }
    dzLoad.active = true;
    dzLoad.startTs = Date.now();
    var zone = $("dropzone"), fill = $("dropzone-fill");
    zone.classList.add("loading");
    zone.classList.remove("hidden");
    $("dropzone-title").textContent = DZ_TITLE_LOADING;
    fill.style.transition = "none";
    fill.style.transform = "scaleX(0)";
    // Reflow erzwingen, damit die folgende Transition ab 0 startet:
    void fill.offsetWidth;
    fill.style.transition = "transform 1000ms linear";
    fill.style.transform = "scaleX(0.9)";
  }

  function dzReset() {
    if (dzLoad.finishTimer) { clearTimeout(dzLoad.finishTimer); dzLoad.finishTimer = null; }
    dzLoad.active = false;
    var zone = $("dropzone"), fill = $("dropzone-fill");
    zone.classList.remove("loading");
    $("dropzone-title").textContent = DZ_TITLE_IDLE;
    fill.style.transition = "none";
    fill.style.transform = "scaleX(0)";
    render();
  }

  function dzFinish() {
    // Erfolgsfall: auf 100 % fuellen, kurz stehen lassen, dann umschalten.
    var fill = $("dropzone-fill");
    fill.style.transition = "transform 150ms ease-out";
    fill.style.transform = "scaleX(1)";
    dzLoad.finishTimer = setTimeout(function () {
      dzLoad.finishTimer = null;
      dzLoad.active = false;
      $("dropzone").classList.remove("loading");
      $("dropzone-title").textContent = DZ_TITLE_IDLE;
      fill.style.transition = "none";
      fill.style.transform = "scaleX(0)";
      render();
      scheduleAutoAdvance();
    }, 200);
  }
```

onEvent, `progress`-Case erweitern:

```js
      case "progress":
        if (evt.method && WATCHDOG_ARM_ON_PROGRESS[evt.method]) armWatchdog(evt.method);
        if (evt.method === "load_mvr" && evt.data && evt.data.phase === "start") dzStart();
        break;
```

`WATCHDOG_ARM_ON_PROGRESS` um `load_mvr: true` ergänzen (das native Öffnen-Dialog-Problem ist dasselbe wie bei run_export: der Watchdog darf erst armiert werden, wenn das Laden wirklich begonnen hat — und Drop-Ladevorgänge bekommen so überhaupt erst einen Watchdog). `WATCHDOG_RESET` ergänzen: `load_mvr: dzReset,`.

In `handleToastEvent` ist nichts weiter nötig: ein Fehler-Toast mit `method: "load_mvr"` läuft über `clearWatchdog("load_mvr", true)` → `WATCHDOG_RESET.load_mvr` → `dzReset()`.

In `applyState`: Der Umschlag Dropzone→Filecard muss auf das Balken-Ende warten. Ersetze den Block `if (!wasLoaded && newState.mvr_loaded) { scheduleAutoAdvance(); }` durch:

```js
    if (!wasLoaded && newState.mvr_loaded) {
      if (dzLoad.active) {
        var elapsed = Date.now() - dzLoad.startTs;
        setTimeout(dzFinish, Math.max(0, DZ_MIN_MS - elapsed));
      } else {
        scheduleAutoAdvance();
      }
    } else if (wasLoaded && !newState.mvr_loaded) {
      cancelAutoAdvance();
    }
```

In `renderSection1` die erste Zeile ersetzen:

```js
    var showDropzone = !s.mvr_loaded || dzLoad.active;
    $("dropzone").classList.toggle("hidden", !showDropzone);
    $("filecard-block").classList.toggle("hidden", !s.mvr_loaded || dzLoad.active);
```

(Solange der Balken läuft, bleibt die Dropzone sichtbar, auch wenn der State schon `mvr_loaded` meldet; `dzFinish` ruft am Ende `render()` und erst dann erscheint die Filecard. Ein Lade-FEHLER führt über `dzReset` zurück zum Normalzustand.)

- [ ] **Step 4: Klick/Tastatur während des Ladens sperren**

Im `dropzone`-Click-Listener und im keydown-Listener als erste Zeile: `if (dzLoad.active) return;`.

- [ ] **Step 5: Smoke-Check**

```powershell
$p = Start-Process -FilePath python -ArgumentList "-m","mvr_enhancer" -PassThru; Start-Sleep -Seconds 10; Stop-Process -Id $p.Id -Force
```

Log auf JS-/evaluate_js-Fehler prüfen. `python -m pytest -q; ruff check .` → grün.

- [ ] **Step 6: Commit**

```bash
git add mvr_enhancer/ui/index.html mvr_enhancer/ui/css/app.css mvr_enhancer/ui/js/app.js
git commit -m "feat(ui): Dropzone wird beim Laden zum Ladebalken (min. 1 s)"
```

---

### Task 8: App-Icon aus dem Handoff

**Files:**
- Modify: `tools/make_icon.py`
- Modify: `build/app.ico` (Ergebnis, eingecheckt)
- Add: `design_handoff_app_icon/**` (Icon-Quelle, committen)
- Test: `tests/test_app_icon.py` (neu)

**Interfaces:**
- Consumes: `design_handoff_app_icon/png/app-icon-{16,24,32,48,64,128,256}.png` (fertige Renderings; 16/24 sind die Pflicht-Small-Variante laut Handoff-README).
- Produces: `build/app.ico` mit exakt diesen 7 PNG-Frames; PyInstaller-Spec referenziert `build/app.ico` bereits — keine Build-Änderung.

- [ ] **Step 1: Failing Test schreiben**

Neuer Test `tests/test_app_icon.py` — parst den ICO-Header (reines struct, kein Pillow):

```python
"""build/app.ico muss die 7 Handoff-PNGs (16..256) als PNG-Frames enthalten."""

import pathlib
import struct

_ICO = pathlib.Path(__file__).resolve().parent.parent / "build" / "app.ico"
_HANDOFF = pathlib.Path(__file__).resolve().parent.parent / "design_handoff_app_icon" / "png"
_EXPECTED_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _read_entries(data: bytes):
    reserved, ico_type, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, ico_type) == (0, 1)
    entries = []
    for i in range(count):
        width, height, _, _, _, bpp, size, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * i
        )
        entries.append({"dim": width or 256, "size": size, "offset": offset})
    return entries


def test_ico_contains_all_handoff_sizes():
    entries = _read_entries(_ICO.read_bytes())
    assert sorted(e["dim"] for e in entries) == _EXPECTED_SIZES


def test_ico_frames_are_verbatim_handoff_pngs():
    data = _ICO.read_bytes()
    frames = {
        e["dim"]: data[e["offset"]:e["offset"] + e["size"]]
        for e in _read_entries(data)
    }
    for size in _EXPECTED_SIZES:
        expected = (_HANDOFF / f"app-icon-{size}.png").read_bytes()
        assert frames[size] == expected, f"Frame {size}px weicht vom Handoff-PNG ab"
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `python -m pytest tests/test_app_icon.py -v`
Expected: FAIL (altes app.ico hat 6 Frames ohne 24px, Inhalte = „G"-Rendering)

- [ ] **Step 3: make_icon.py umschreiben**

Das PowerShell-Rendering (`_RENDER_PS1`, `_render_pngs`, `_GRADIENT_*`) komplett entfernen; `_build_ico` bleibt unverändert. Neue Quelle:

```python
_SIZES = (16, 24, 32, 48, 64, 128, 256)
_PNG_DIR = pathlib.Path(__file__).resolve().parent.parent / "design_handoff_app_icon" / "png"


def _load_frames() -> list[tuple[int, bytes]]:
    """Liest die fertigen Handoff-PNGs (16/24 = Small-Variante, Rest = Master)."""
    frames = []
    for size in _SIZES:
        png = _PNG_DIR / f"app-icon-{size}.png"
        if not png.is_file():
            raise SystemExit(f"Handoff-PNG fehlt: {png}")
        frames.append((size, png.read_bytes()))
    return frames
```

`main()` entsprechend verschlanken (kein tempfile, kein win32-Check — das Packen ist plattformneutral); Modul-Docstring aktualisieren: Quelle ist jetzt `design_handoff_app_icon/` (Motiv „3a", fertige Renderings), das Skript packt nur noch den PNG-in-ICO-Container; Ergebnis bleibt eingecheckt.

- [ ] **Step 4: Icon bauen + Test grün**

Run: `python tools/make_icon.py; python -m pytest tests/test_app_icon.py -v`
Expected: „Icon geschrieben: … 7 Groessen: 16, 24, 32, 48, 64, 128, 256"; Tests PASS

- [ ] **Step 5: Suite + Lint**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 6: Commit (inkl. Icon-Handoff-Assets)**

```bash
git add tools/make_icon.py build/app.ico tests/test_app_icon.py design_handoff_app_icon
git commit -m "feat(icon): App-Icon aus dem Design-Handoff (Motiv 3a) in build/app.ico packen"
```

---

### Task 9: Doku + Version 0.2.0

**Files:**
- Modify: `pyproject.toml` (Z.7: `version = "0.1.0"`)
- Modify: `README.md`

**Interfaces:**
- Consumes: alles Vorherige.
- Produces: Release-fertiger Stand.

- [ ] **Step 1: Version bump**

`pyproject.toml`: `version = "0.2.0"`.

- [ ] **Step 2: README aktualisieren**

1. Im Bedienungs-Abschnitt: Drag&Drop erwähnen („MVR-Datei auf die Ablagefläche ziehen oder klicken").
2. Neuer Unterabschnitt „Export-Modi" (beim Export-Abschnitt):
   - **Single Layer** (Standard): alles in einem Layer „MVR Enhancer Export" — Fixtures (optional nach Position gruppiert) plus eine „3D"-Gruppe mit allen 3D-Objekten.
   - **Per Layer**: Fixtures im Layer „MVR Enhancer Export"; jeder Original-Layer mit 3D-Objekten bleibt erhalten und enthält eine „3D"-Gruppe (erscheint in grandMA3 als Grouping-Fixture). Original-Layer ohne 3D-Objekte entfallen.
3. Im Abschnitt „Bekannte Grenzen" ergänzen: „Ein MVR-Import kann vorhandene grandMA3-Show-Layer nicht löschen — leere Layer in einer bestehenden Show stammen aus früheren Importen und müssen dort manuell entfernt werden."

- [ ] **Step 3: Suite + Lint final**

Run: `python -m pytest -q; ruff check .` → grün

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml README.md
git commit -m "docs: Export-Modi + Drag&Drop dokumentieren, Version 0.2.0"
```
