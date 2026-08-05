"""Tests fuer enricher.py (Typ-basierte Anreicherung, Orphan-Cleanup, Report).

Jeder Test baut ein MVR (und ggf. eine GDTF-Bibliothek) ueber ``tests.builders``,
ruft ``enrich_mvr`` auf und liest das Ergebnis-ZIP ueber eine Temp-Datei mit
``read_mvr`` zurueck (Roundtrip), um sicherzustellen, dass der Export selbst
wieder ein gueltiges, parsebares MVR ist. Die UUID-Reproduzierbarkeit und die
Gruppen-Struktur pruefen zusaetzlich direkt im rohen XML, da ``MvrScene``
Layer-/GroupObject-UUIDs nicht eigenstaendig abbildet.
"""

import io
import uuid
import zipfile
from xml.etree import ElementTree as ET

from mvr_enhancer.core.analysis import aggregate_fixture_types
from mvr_enhancer.core.enricher import enrich_mvr
from mvr_enhancer.core.gdtf import load_gdtf_library
from mvr_enhancer.core.models import Assignment
from mvr_enhancer.core.mvr_reader import read_mvr
from tests.builders import build_gdtf, build_mvr


def _types_by_name(types):
    return {t.name: t for t in types}


def test_poison_elements_stripped(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2},
        ],
        poison=True,
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    assert len(reread.fixtures) == 2
    for fixture in reread.fixtures:
        assert fixture.element.find("CustomCommands") is None
        assert fixture.element.find("Position") is None

    assert result.report.cleanup.stripped_tag_counts == {
        "CustomCommands": 2,
        "Position": 2,
    }


def test_removed_type_dropped(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2},
            {"name": "Wash B", "uuid": "33333333-3333-3333-3333-333333333333",
             "address": 3},
        ],
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    by_name = _types_by_name(types)
    assignments = {
        by_name["Spot A"].key: Assignment(gdtf_name=None, removed=True),
        by_name["Wash B"].key: Assignment(gdtf_name="Beam One", mode_name="Mode 1"),
    }

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    names = {f.name for f in reread.fixtures}
    assert names == {"Wash B"}
    assert len(reread.fixtures) == 1

    assert result.report.cleanup.removed_type_names == ["Spot A"]
    assert result.report.cleanup.removed_fixture_count == 2
    assert result.report.matched_fixtures == 1
    assert result.report.total_fixtures == 3


def test_unassigned_type_dropped_without_removed_flag(tmp_path):
    # A type with an Assignment placeholder that has no gdtf_name yet (e.g.
    # a still-open row in the UI) must be dropped like an explicitly removed
    # one, but must NOT show up in removed_type_names (that list is reserved
    # for explicit removed=True types per the brief).
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
            {"name": "Wash B", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2},
        ],
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    by_name = _types_by_name(types)
    assignments = {
        by_name["Spot A"].key: Assignment(gdtf_name=None, mode_name=None, removed=False),
        by_name["Wash B"].key: Assignment(gdtf_name="Beam One", mode_name="Mode 1"),
    }

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    assert {f.name for f in reread.fixtures} == {"Wash B"}
    assert result.report.cleanup.removed_type_names == []
    assert result.report.cleanup.removed_fixture_count == 1
    assert result.report.matched_fixtures == 1
    assert result.report.total_fixtures == 2


def test_orphan_gdtf_removed(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
        ],
        embedded={
            "Orphan@Old@r0.gdtf": b"orphaned gdtf bytes",
            "mesh1.glb": b"fake mesh bytes",
        },
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)

    with zipfile.ZipFile(out_path) as zf:
        names = set(zf.namelist())

    assert "Orphan@Old@r0.gdtf" not in names
    assert "mesh1.glb" in names
    assert "Testlight@Beam One@rev1.gdtf" in names

    assert result.report.cleanup.orphan_gdtf_names == ["Orphan@Old@r0.gdtf"]
    assert result.report.mesh_count == 1
    assert result.report.embedded_gdtf_count == 1


def test_assigned_gdtf_embedded_and_spec_set(tmp_path):
    library_dir = tmp_path / "library"
    gdtf_path = build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
        modes=(("Mode 1", 16), ("Mode 2", 32)),
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 5},
        ],
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 2")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    assert len(reread.fixtures) == 1
    fixture = reread.fixtures[0]
    assert fixture.gdtf_spec == "Testlight@Beam One@rev1.gdtf"
    assert fixture.gdtf_mode == "Mode 2"

    with zipfile.ZipFile(out_path) as zf:
        embedded_bytes = zf.read("Testlight@Beam One@rev1.gdtf")
    assert embedded_bytes == gdtf_path.read_bytes()

    assert result.report.embedded_gdtf_count == 1


def test_mode_fallback_reported(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
        modes=(("Mode 1", 16), ("Mode 2", 32)),
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2},
            {"name": "Spot A", "uuid": "33333333-3333-3333-3333-333333333333",
             "address": 3},
        ],
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name=None)}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    assert len(reread.fixtures) == 3
    for fixture in reread.fixtures:
        assert fixture.gdtf_mode == "Mode 1"

    assert len(result.report.fallbacks) == 1
    fallback = result.report.fallbacks[0]
    assert fallback.type_name == "Spot A"
    assert fallback.count == 3
    assert fallback.gdtf_name == "Beam One"
    assert fallback.mode_name == "Mode 1"


def test_reproducible_uuids(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "position_uuid": "aaaaaaaa-0000-0000-0000-000000000000"},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2, "position_uuid": "bbbbbbbb-0000-0000-0000-000000000000"},
        ],
        aux_positions={
            "aaaaaaaa-0000-0000-0000-000000000000": "Truss 1",
            "bbbbbbbb-0000-0000-0000-000000000000": "Truss 2",
        },
    )

    def _run():
        scene = read_mvr(str(mvr_path))
        types = aggregate_fixture_types(scene)
        key = types[0].key
        assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}
        return enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    result1 = _run()
    result2 = _run()

    def _uuids(data: bytes) -> tuple[str, list[str]]:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_bytes = zf.read("GeneralSceneDescription.xml")
        root = ET.fromstring(xml_bytes)
        layer = root.find("Scene/Layers/Layer")
        groups = root.findall("Scene/Layers/Layer/ChildList/GroupObject")
        return layer.get("uuid"), sorted(g.get("uuid") for g in groups)

    layer_uuid_1, group_uuids_1 = _uuids(result1.data)
    layer_uuid_2, group_uuids_2 = _uuids(result2.data)

    assert layer_uuid_1 == layer_uuid_2
    assert group_uuids_1 == group_uuids_2
    assert layer_uuid_1 == str(uuid.uuid5(uuid.NAMESPACE_DNS, "layer_MVR Enhancer Export"))
    assert group_uuids_1 == sorted([
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "group_Truss 1")),
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "group_Truss 2")),
    ])


def test_grouping_by_position(tmp_path):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "position_uuid": "aaaaaaaa-0000-0000-0000-000000000000"},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2, "position_uuid": "bbbbbbbb-0000-0000-0000-000000000000"},
        ],
        aux_positions={
            "aaaaaaaa-0000-0000-0000-000000000000": "Truss 1",
            "bbbbbbbb-0000-0000-0000-000000000000": "Truss 2",
        },
    )

    def _fresh():
        scene = read_mvr(str(mvr_path))
        types = aggregate_fixture_types(scene)
        key = types[0].key
        assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}
        return scene, types, assignments

    scene, types, assignments = _fresh()
    grouped_result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library, group_by_position=True,
    )
    with zipfile.ZipFile(io.BytesIO(grouped_result.data)) as zf:
        grouped_xml = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    groups = grouped_xml.findall("Scene/Layers/Layer/ChildList/GroupObject")
    assert {g.get("name") for g in groups} == {"Truss 1", "Truss 2"}
    for group in groups:
        fixtures_in_group = group.findall("ChildList/Fixture")
        assert len(fixtures_in_group) == 1
    assert grouped_result.report.position_group_count == 2

    scene, types, assignments = _fresh()
    flat_result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library, group_by_position=False,
    )
    with zipfile.ZipFile(io.BytesIO(flat_result.data)) as zf:
        flat_xml = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    assert flat_xml.findall("Scene/Layers/Layer/ChildList/GroupObject") == []
    flat_fixtures = flat_xml.findall("Scene/Layers/Layer/ChildList/Fixture")
    assert len(flat_fixtures) == 2
    assert flat_result.report.position_group_count == 0
