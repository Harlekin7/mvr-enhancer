from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile, is_zipfile

import pygdtf

from tests.builders import build_gdtf, build_mvr


def test_gdtf_readable_by_pygdtf(tmp_path):
    path = build_gdtf(tmp_path / "beam.gdtf")

    fixture_type = pygdtf.FixtureType(str(path))

    assert fixture_type.name == "Beam One"
    assert fixture_type.manufacturer == "Testlight"
    assert len(fixture_type.dmx_modes) == 2

    modes_by_name = {mode.name: mode for mode in fixture_type.dmx_modes}
    assert modes_by_name["Mode 1"].dmx_channels_count == 16
    assert modes_by_name["Mode 2"].dmx_channels_count == 32


def test_gdtf_custom_parameters(tmp_path):
    path = build_gdtf(
        tmp_path / "custom.gdtf",
        manufacturer="Acme Lighting",
        name="Spot 250",
        revision="rev2",
        modes=(("Basic", 4),),
    )

    fixture_type = pygdtf.FixtureType(str(path))

    assert fixture_type.manufacturer == "Acme Lighting"
    assert fixture_type.name == "Spot 250"
    assert len(fixture_type.dmx_modes) == 1
    assert fixture_type.dmx_modes[0].name == "Basic"
    assert fixture_type.dmx_modes[0].dmx_channels_count == 4


def test_mvr_is_zip_with_xml(tmp_path):
    fixtures = [
        {
            "name": "Fixture 1",
            "uuid": str(uuid4()),
            "gdtf_spec": "Testlight@Beam One@rev1.gdtf",
            "gdtf_mode": "Mode 1",
            "address": 1,
            "position_uuid": "pos-1",
            "layer": "Layer 1",
        },
        {
            "name": "Fixture 2",
            "uuid": str(uuid4()),
            "gdtf_spec": "Testlight@Beam One@rev1.gdtf",
            "gdtf_mode": "Mode 2",
            "address": 17,
            "position_uuid": "pos-1",
            "layer": "Layer 1",
        },
    ]

    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=fixtures,
        aux_positions={"pos-1": "FOH Truss"},
    )

    assert is_zipfile(path)
    with ZipFile(path) as zf:
        assert "GeneralSceneDescription.xml" in zf.namelist()
        xml_bytes = zf.read("GeneralSceneDescription.xml")

    root = ElementTree.fromstring(xml_bytes)
    assert root.tag == "GeneralSceneDescription"
    assert root.get("verMajor") == "1"
    assert root.get("verMinor") == "5"

    fixture_els = root.findall(".//Fixture")
    assert len(fixture_els) == 2
    assert {f.get("name") for f in fixture_els} == {"Fixture 1", "Fixture 2"}

    for fixture_el in fixture_els:
        assert fixture_el.find("GDTFSpec").text == "Testlight@Beam One@rev1.gdtf"
        assert fixture_el.find("Addresses/Address") is not None
        assert fixture_el.find("Addresses/Address").get("break") == "0"
        assert fixture_el.find("Matrix") is not None
        assert fixture_el.find("CustomCommands") is None

    aux_data_el = root.find(".//AUXData")
    assert aux_data_el is not None
    assert root.find("Scene/AUXData") is aux_data_el
    position_defs = aux_data_el.findall("Position")
    assert len(position_defs) == 1
    assert position_defs[0].get("uuid") == "pos-1"
    assert position_defs[0].get("name") == "FOH Truss"


def test_mvr_poison_adds_custom_commands_and_dangling_position(tmp_path):
    fixtures = [
        {
            "name": "Poisoned",
            "uuid": str(uuid4()),
            "gdtf_spec": "Testlight@Beam One@rev1.gdtf",
            "gdtf_mode": "Mode 1",
            "address": 1,
            "position_uuid": "pos-1",
            "layer": "Layer 1",
        }
    ]

    path = build_mvr(
        tmp_path / "poison.mvr",
        fixtures=fixtures,
        aux_positions={"pos-1": "FOH Truss"},
        poison=True,
    )

    with ZipFile(path) as zf:
        xml_bytes = zf.read("GeneralSceneDescription.xml")

    root = ElementTree.fromstring(xml_bytes)
    fixture_el = root.find(".//Fixture")

    custom_commands_el = fixture_el.find("CustomCommands")
    assert custom_commands_el is not None
    assert custom_commands_el.find("CustomCommand").text == "f 0.000000"

    position_el = fixture_el.find("Position")
    assert position_el is not None
    aux_uuids = {p.get("uuid") for p in root.find(".//AUXData").findall("Position")}
    assert position_el.text not in aux_uuids


def test_mvr_omits_aux_data_when_no_positions_given(tmp_path):
    fixtures = [
        {
            "name": "Fixture 1",
            "uuid": str(uuid4()),
            "gdtf_spec": "Testlight@Beam One@rev1.gdtf",
            "gdtf_mode": "Mode 1",
            "address": 1,
            "layer": "Layer 1",
        }
    ]

    path = build_mvr(tmp_path / "no_aux.mvr", fixtures=fixtures)

    with ZipFile(path) as zf:
        xml_bytes = zf.read("GeneralSceneDescription.xml")

    root = ElementTree.fromstring(xml_bytes)
    assert root.find(".//AUXData") is None


def test_mvr_embedded_files_are_added_to_zip(tmp_path):
    path = build_mvr(
        tmp_path / "with_embedded.mvr",
        fixtures=[],
        embedded={
            "Orphan@Old@r0.gdtf": b"fake-gdtf-bytes",
            "mesh1.glb": b"fake-glb-bytes",
        },
    )

    with ZipFile(path) as zf:
        names = zf.namelist()
        assert "Orphan@Old@r0.gdtf" in names
        assert "mesh1.glb" in names
        assert zf.read("mesh1.glb") == b"fake-glb-bytes"
