"""Tests fuer enricher.py (Typ-basierte Anreicherung, Orphan-Cleanup, Report).

Jeder Test baut ein MVR (und ggf. eine GDTF-Bibliothek) ueber ``tests.builders``,
ruft ``enrich_mvr`` auf und liest das Ergebnis-ZIP ueber eine Temp-Datei mit
``read_mvr`` zurueck (Roundtrip), um sicherzustellen, dass der Export selbst
wieder ein gueltiges, parsebares MVR ist. Die UUID-Reproduzierbarkeit und die
Gruppen-Struktur pruefen zusaetzlich direkt im rohen XML, da ``MvrScene``
Layer-/GroupObject-UUIDs nicht eigenstaendig abbildet.
"""

import io
import re
import uuid
import zipfile
from xml.etree import ElementTree as ET

from mvr_enhancer.core.analysis import aggregate_fixture_types
from mvr_enhancer.core.enricher import _IDENTITY_MATRIX, enrich_mvr
from mvr_enhancer.core.gdtf import load_gdtf_library
from mvr_enhancer.core.models import Assignment
from mvr_enhancer.core.mvr_reader import MvrFixture, MvrScene, read_mvr
from tests.builders import _IDENTITY_MATRIX as _FIXTURE_IDENTITY_MATRIX
from tests.builders import build_gdtf, build_mvr


def _types_by_name(types):
    return {t.name: t for t in types}


def _rewrite_scene_xml(mvr_path, transform) -> None:
    """Rewrites ``GeneralSceneDescription.xml`` inside an existing MVR zip.

    Used to inject XML shapes ``tests.builders.build_mvr`` doesn't support
    directly (a ``<Fixture>`` nested inside a ``<SceneObject>``, a bare
    ``<UserData>`` block) by parsing the current root, letting ``transform``
    mutate it in place, and re-writing the zip with all original entries
    plus the updated XML.
    """
    with zipfile.ZipFile(mvr_path) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}
    root = ET.fromstring(entries["GeneralSceneDescription.xml"])
    transform(root)
    entries["GeneralSceneDescription.xml"] = ET.tostring(
        root, encoding="UTF-8", xml_declaration=True
    )
    with zipfile.ZipFile(mvr_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


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

    # Matrix (3D position) must survive untouched from the source MVR.
    assert fixture.matrix == _FIXTURE_IDENTITY_MATRIX
    # FixtureID/UnitNumber are ensured present (this app has no channel/unit
    # model to renumber them with, so they default to "0" when missing).
    assert fixture.element.find("FixtureID").text == "0"
    assert fixture.element.find("UnitNumber").text == "0"
    # Address is absolute and carries the normalized break="0" attribute.
    address_el = fixture.element.find("Addresses/Address")
    assert address_el.get("break") == "0"
    assert address_el.text == "5"

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

    # Scene child order per MVR spec sequence: AUXData before Layers.
    scene_child_tags = [child.tag for child in grouped_xml.find("Scene")]
    assert scene_child_tags.index("AUXData") < scene_child_tags.index("Layers")

    # AUXData (the Position definitions) must survive unchanged.
    aux_positions_out = {
        pos_el.get("uuid"): pos_el.get("name")
        for pos_el in grouped_xml.findall("Scene/AUXData/Position")
    }
    assert aux_positions_out == {
        "aaaaaaaa-0000-0000-0000-000000000000": "Truss 1",
        "bbbbbbbb-0000-0000-0000-000000000000": "Truss 2",
    }

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


def test_fuzzy_gdtf_name_resolves_mode_and_warns(tmp_path):
    # Reviewer-probe regression: an Assignment.gdtf_name that is NOT an exact
    # library dict key (here "Beam" vs. the library's actual "Beam One") must
    # still resolve GDTFMode from the modes of whatever GDTF file actually
    # gets embedded — not leave the source MVR's stale GDTFMode text in place
    # with no warning, which is what happened when `matched` stayed None on
    # an exact-key miss even though `find_gdtf_file` went on to fuzzy-resolve
    # and embed "Beam One" anyway.
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
             "address": 1, "gdtf_mode": "Bogus Legacy Mode 99"},
        ],
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam", mode_name=None)}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)
    reread = read_mvr(str(out_path))

    assert len(reread.fixtures) == 1
    fixture = reread.fixtures[0]
    assert fixture.gdtf_spec == "Testlight@Beam One@rev1.gdtf"
    assert fixture.gdtf_mode == "Mode 1"
    assert fixture.gdtf_mode != "Bogus Legacy Mode 99"

    assert len(result.report.fallbacks) == 1
    fallback = result.report.fallbacks[0]
    assert fallback.gdtf_name == "Beam One"
    assert fallback.mode_name == "Mode 1"
    assert fallback.count == 1


def test_nested_fixture_gdtf_and_poison_survive_orphan_cleanup(tmp_path):
    # Reviewer-probe regression: mvr_reader only recurses into GroupObject,
    # so a <Fixture> nested inside an opaque non-fixture element (Truss,
    # SceneObject, ...) is never collected into scene.fixtures — it rides
    # along untouched inside scene.non_fixture_elements and ends up in the
    # rebuilt "3D" GroupObject verbatim. The orphan-cleanup reference set and
    # the CustomCommands/Position strip pass must still reach it.
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
        embedded={"VW@Nested@r0.gdtf": b"nested gdtf bytes"},
    )

    def _inject_nested_fixture(root: ET.Element) -> None:
        child_list = root.find("Scene/Layers/Layer/ChildList")
        scene_object = ET.SubElement(child_list, "SceneObject", {"uuid": str(uuid.uuid4())})
        nested_child_list = ET.SubElement(scene_object, "ChildList")
        nested_fixture = ET.SubElement(
            nested_child_list, "Fixture",
            {"name": "Nested Light", "uuid": "99999999-9999-9999-9999-999999999999"},
        )
        ET.SubElement(nested_fixture, "GDTFSpec").text = "VW@Nested@r0.gdtf"
        ET.SubElement(nested_fixture, "GDTFMode").text = "Mode 1"
        custom_commands = ET.SubElement(nested_fixture, "CustomCommands")
        ET.SubElement(custom_commands, "CustomCommand").text = "f 0.000000"
        ET.SubElement(nested_fixture, "Position").text = str(uuid.uuid4())

    _rewrite_scene_xml(mvr_path, _inject_nested_fixture)

    scene = read_mvr(str(mvr_path))
    # Sanity check on the premise: the nested Fixture is NOT collected as a
    # top-level MvrFixture instance (it rides inside non_fixture_elements).
    assert len(scene.fixtures) == 1
    assert len(scene.non_fixture_elements) == 1

    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)

    with zipfile.ZipFile(out_path) as zf:
        names = set(zf.namelist())
        xml_root = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    assert "VW@Nested@r0.gdtf" in names
    assert result.report.cleanup.orphan_gdtf_names == []

    nested_fixture_el = xml_root.find(".//GroupObject[@name='3D']//Fixture")
    assert nested_fixture_el is not None
    assert nested_fixture_el.get("name") == "Nested Light"
    assert nested_fixture_el.find("CustomCommands") is None
    assert nested_fixture_el.find("Position") is None
    assert result.report.cleanup.stripped_tag_counts.get("CustomCommands", 0) >= 1
    assert result.report.cleanup.stripped_tag_counts.get("Position", 0) >= 1


def test_percent_encoded_gdtf_reference_cleaned_and_kept(tmp_path):
    # Bundled review item: %40 -> @ cleaning must apply even when GDTF
    # resolution fails entirely (assignment.gdtf_name matches nothing in the
    # library) — the fixture's original, still percent-encoded GDTFSpec is
    # left untouched by _update_fixture_element (no resolved filename to set),
    # but the full-tree decode pass must still clean it, and orphan-cleanup
    # must recognize the (now-decoded) reference and keep the correspondingly
    # named embedded file instead of dropping it as an orphan.
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
             "address": 1, "gdtf_spec": "Robe%40Robin%40r1.gdtf"},
        ],
        embedded={"Robe%40Robin%40r1.gdtf": b"robe gdtf bytes"},
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    # "NoSuchGdtf" scores 0.0 against the only library entry ("Beam One"),
    # well below the 0.6 auto-match threshold -> resolution fails entirely.
    assignments = {key: Assignment(gdtf_name="NoSuchGdtf", mode_name=None)}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    out_path = tmp_path / "out.mvr"
    out_path.write_bytes(result.data)

    with zipfile.ZipFile(out_path) as zf:
        names = set(zf.namelist())
        xml_root = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    assert "Robe@Robin@r1.gdtf" in names
    assert "Robe%40Robin%40r1.gdtf" not in names
    assert result.report.cleanup.orphan_gdtf_names == []

    fixture_el = xml_root.find(".//Fixture")
    assert fixture_el.find("GDTFSpec").text == "Robe@Robin@r1.gdtf"


#: An MVR ``<Matrix>`` is 4 groups of 3 floats — ``{u}{v}{w}{o}``: the three
#: basis vectors followed by the translation/origin (DIN SPEC 15801 / MVR 1.5+).
#: Asserted as a SHAPE, deliberately not compared against any constant, so a
#: wrong-shaped constant on either side can't make the test pass.
_MVR_MATRIX_RE = re.compile(
    r"^(?:\{\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\}){4}$"
)


def test_emitted_matrix_shape_is_four_groups_of_three(tmp_path):
    """Every ``<Matrix>`` the enricher emits must have MVR's 4×3 shape."""
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
        ],
        aux_positions={"aaaaaaaa-0000-0000-0000-000000000000": "Truss 1"},
        embedded={"mesh1.glb": b"mesh bytes"},
    )

    scene = read_mvr(str(mvr_path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        root = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    # Layer + at least one GroupObject (position group) carry a Matrix.
    emitted = [
        el.text or ""
        for el in root.iter("Matrix")
        if el.text
    ]
    assert emitted, "expected the export to emit at least one <Matrix>"
    for text in emitted:
        assert _MVR_MATRIX_RE.match(text.strip()), text


def test_builder_identity_matrix_has_mvr_shape():
    """The test-fixture builder must not hand the parsers a 4×4 matrix."""
    assert _MVR_MATRIX_RE.match(_FIXTURE_IDENTITY_MATRIX)


def test_export_never_writes_traversal_entry_names(tmp_path):
    """No ``writestr``/``write`` target may escape the archive root.

    ``mvr_reader`` filters traversal entries on the way IN, but the export
    side URL-decodes names again (``_clean_gdtf_name``) — a name that looked
    harmless as a raw ZIP entry can decode into a real ``../``. The embedded
    files are injected directly here so the export-side guard is exercised
    on its own, independently of the reader's (now also hardened) filter.
    """
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
             "address": 1, "gdtf_spec": "%2E%2E%2F..%2Fevil.gdtf"},
        ],
    )

    scene = read_mvr(str(mvr_path))
    # Direct injection: the reader would (and now does) reject these itself.
    scene.embedded_files["%2E%2E%2F..%2Fevil.gdtf"] = b"zip-slip gdtf"
    scene.embedded_files["../../evil-mesh.glb"] = b"zip-slip mesh"
    scene.embedded_files["C:\\windows\\system32\\evil.txt"] = b"absolute"
    scene.embedded_files["/etc/passwd"] = b"rooted"
    scene.embedded_files["mesh1.glb"] = b"harmless mesh"

    types = aggregate_fixture_types(scene)
    key = types[0].key
    # "NoSuchGdtf" resolves to nothing, so the fixture keeps its original
    # (percent-encoded, traversing) GDTFSpec — which puts the decoded
    # "../../evil.gdtf" into the kept-reference set and would previously have
    # been re-emitted verbatim by zf.writestr(clean_name, ...).
    assignments = {key: Assignment(gdtf_name="NoSuchGdtf", mode_name=None)}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        names = zf.namelist()

    for name in names:
        normalized = name.replace("\\", "/")
        assert not normalized.startswith("/"), name
        assert ".." not in normalized.split("/"), name
        assert not (len(normalized) > 1 and normalized[1] == ":"), name

    assert "mesh1.glb" in names
    assert "GeneralSceneDescription.xml" in names
    # The skipped entries are reported as discarded, not silently dropped.
    assert "../../evil.gdtf" in result.report.cleanup.orphan_gdtf_names


def test_user_data_survives(tmp_path):
    # Bundled review item: UserData must survive the rebuild. The builder
    # doesn't support emitting UserData directly, so inject it into the raw
    # XML after building a normal MVR.
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
    )

    def _inject_user_data(root: ET.Element) -> None:
        user_data = ET.Element("UserData")
        ET.SubElement(user_data, "Data", {"provider": "Test", "value": "marker-123"})
        root.insert(0, user_data)

    _rewrite_scene_xml(mvr_path, _inject_user_data)

    scene = read_mvr(str(mvr_path))
    assert scene.user_data is not None

    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(scene, types, assignments, str(library_dir), gdtf_library)

    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        root = ET.fromstring(zf.read("GeneralSceneDescription.xml"))

    user_data_el = root.find("UserData")
    assert user_data_el is not None
    data_el = user_data_el.find("Data")
    assert data_el is not None
    assert data_el.get("value") == "marker-123"


def _export_root(result):
    """Parst ``GeneralSceneDescription.xml`` direkt aus einem ``EnrichResult``."""
    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        return ET.fromstring(zf.read("GeneralSceneDescription.xml"))


def test_per_layer_keeps_original_layers_with_3d_grouping(tmp_path):
    # Szene: 1 zugeordnete Fixture in "Rig A", SceneObjects in "Rig A" und
    # "Rig B", Layer "Leer" ohne Nicht-Fixture-Elemente (nur eine entfernte
    # Fixture), Matrix nur auf "Rig A".
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

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
    by_name = _types_by_name(types)
    assignments = {
        by_name["Spot 1"].key: Assignment(gdtf_name="Beam One", mode_name="Mode 1"),
        by_name["Plugbox"].key: Assignment(gdtf_name=None, removed=True),
    }
    result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library,
        group_by_position=False, layer_mode="per_layer",
    )

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
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr = build_mvr(
        tmp_path / "src.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "position_uuid": "aaaaaaaa-0000-0000-0000-000000000000",
             "layer": "Rig A"},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2, "position_uuid": "bbbbbbbb-0000-0000-0000-000000000000",
             "layer": "Rig A"},
        ],
        scene_objects=[{"name": "Truss A", "layer": "Rig A"}],
        aux_positions={
            "aaaaaaaa-0000-0000-0000-000000000000": "Truss 1",
            "bbbbbbbb-0000-0000-0000-000000000000": "Truss 2",
        },
    )
    scene = read_mvr(str(mvr))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library,
        group_by_position=True, layer_mode="per_layer",
    )

    root = _export_root(result)
    layer_els = root.findall("./Scene/Layers/Layer")
    assert [layer.get("name") for layer in layer_els] == ["MVR Enhancer Export", "Rig A"]

    export_layer = layer_els[0]
    position_groups = export_layer.findall("./ChildList/GroupObject")
    assert {g.get("name") for g in position_groups} == {"Truss 1", "Truss 2"}
    for group in position_groups:
        assert len(group.findall("./ChildList/Fixture")) == 1
    assert result.report.position_group_count == 2

    rig_a = layer_els[1]
    rig_a_groups = rig_a.findall("./ChildList/GroupObject")
    assert len(rig_a_groups) == 1 and rig_a_groups[0].get("name") == "3D"
    assert [el.get("name") for el in rig_a_groups[0].findall("./ChildList/SceneObject")] == ["Truss A"]


def test_unknown_layer_mode_falls_back_to_single(tmp_path):
    # layer_mode="quatsch" erzeugt exakt denselben Baum wie layer_mode="single"
    # (ein Layer, 3D-Gruppe im Export-Layer).
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    mvr = build_mvr(
        tmp_path / "src.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "layer": "Rig A"},
        ],
        scene_objects=[{"name": "Truss A", "layer": "Rig A"}],
    )

    def _fresh():
        scene = read_mvr(str(mvr))
        types = aggregate_fixture_types(scene)
        key = types[0].key
        assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}
        return scene, types, assignments

    scene, types, assignments = _fresh()
    single_result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library, layer_mode="single",
    )

    scene, types, assignments = _fresh()
    unknown_result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library, layer_mode="quatsch",
    )

    single_xml = ET.tostring(_export_root(single_result))
    unknown_xml = ET.tostring(_export_root(unknown_result))
    assert unknown_xml == single_xml

    root = _export_root(unknown_result)
    layer_els = root.findall("./Scene/Layers/Layer")
    assert [layer.get("name") for layer in layer_els] == ["MVR Enhancer Export"]
    assert layer_els[0].find("./ChildList/GroupObject[@name='3D']") is not None


def test_per_layer_without_layer_infos_falls_back_to_single_3d_group(tmp_path):
    # Defensive: MvrScene mit non_fixture_elements, aber leerer layers-Liste
    # (synthetisch konstruiert) -> Elemente landen in der 3D-Gruppe des
    # Export-Layers statt verloren zu gehen.
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Beam One@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    gdtf_library = load_gdtf_library(str(library_dir), force_reload=True)

    fixture_el = ET.Element(
        "Fixture",
        {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111"},
    )
    ET.SubElement(fixture_el, "GDTFSpec").text = ""
    ET.SubElement(fixture_el, "GDTFMode").text = ""
    addresses_el = ET.SubElement(fixture_el, "Addresses")
    ET.SubElement(addresses_el, "Address", {"break": "0"}).text = "1"
    ET.SubElement(fixture_el, "Matrix").text = _FIXTURE_IDENTITY_MATRIX

    fixture = MvrFixture(
        element=fixture_el,
        uuid=fixture_el.get("uuid"),
        name="Spot A",
        gdtf_spec="",
        gdtf_mode="",
        dmx_address=1,
        matrix=_FIXTURE_IDENTITY_MATRIX,
    )
    non_fixture_el = ET.Element(
        "SceneObject", {"name": "Truss A", "uuid": str(uuid.uuid4())},
    )
    scene = MvrScene(fixtures=[fixture], non_fixture_elements=[non_fixture_el], layers=[])

    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Beam One", mode_name="Mode 1")}

    result = enrich_mvr(
        scene, types, assignments, str(library_dir), gdtf_library, layer_mode="per_layer",
    )

    root = _export_root(result)
    layer_els = root.findall("./Scene/Layers/Layer")
    assert [layer.get("name") for layer in layer_els] == ["MVR Enhancer Export"]

    export_layer = layer_els[0]
    group_3d = export_layer.find("./ChildList/GroupObject[@name='3D']")
    assert group_3d is not None
    assert [el.get("name") for el in group_3d.findall("./ChildList/SceneObject")] == ["Truss A"]
