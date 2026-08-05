"""Programmatic test-fixture builders for minimal MVR/GDTF files.

These helpers write small, spec-shaped MVR and GDTF ZIP packages so that
tests exercising the real parsers (pygdtf and this project's own MVR
reader) have deterministic, controllable input without depending on real
manufacturer files.
"""

import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# Identity matrix in the GDTF/MVR "4 groups of 4 floats" text format.
_IDENTITY_MATRIX = (
    "{1.000000,0.000000,0.000000,0.000000}"
    "{0.000000,1.000000,0.000000,0.000000}"
    "{0.000000,0.000000,1.000000,0.000000}"
    "{0.000000,0.000000,0.000000,1.000000}"
)


def build_gdtf(
    path: Path,
    *,
    manufacturer: str = "Testlight",
    name: str = "Beam One",
    revision: str = "rev1",
    modes: tuple[tuple[str, int], ...] = (("Mode 1", 16), ("Mode 2", 32)),
) -> Path:
    """Write a minimal, pygdtf-readable .gdtf package (ZIP + description.xml).

    Each entry in ``modes`` is a ``(mode_name, channel_count)`` pair. The
    written DMXMode gets exactly ``channel_count`` single-byte DMXChannel
    children (Offset 1..N) attached to one root Geometry, so that
    ``pygdtf`` reports ``dmx_channels_count == channel_count`` per mode.
    """
    path = Path(path)

    gdtf_root = ET.Element("GDTF", {"DataVersion": "1.2"})
    fixture_type_el = ET.SubElement(
        gdtf_root,
        "FixtureType",
        {
            "Name": name,
            "ShortName": name,
            "LongName": name,
            "Manufacturer": manufacturer,
            "Description": f"{manufacturer} {name}",
            "FixtureTypeID": str(
                uuid.uuid5(uuid.NAMESPACE_OID, f"{manufacturer}/{name}")
            ),
        },
    )

    revisions_el = ET.SubElement(fixture_type_el, "Revisions")
    ET.SubElement(revisions_el, "Revision", {"Text": revision})

    geometries_el = ET.SubElement(fixture_type_el, "Geometries")
    ET.SubElement(geometries_el, "Geometry", {"Name": "Base"})

    dmx_modes_el = ET.SubElement(fixture_type_el, "DMXModes")
    for mode_name, channel_count in modes:
        mode_el = ET.SubElement(
            dmx_modes_el, "DMXMode", {"Name": mode_name, "Geometry": "Base"}
        )
        channels_el = ET.SubElement(mode_el, "DMXChannels")
        for offset in range(1, channel_count + 1):
            channel_el = ET.SubElement(
                channels_el,
                "DMXChannel",
                {"DMXBreak": "1", "Offset": str(offset), "Geometry": "Base"},
            )
            ET.SubElement(channel_el, "LogicalChannel", {"Attribute": "Dimmer"})

    xml_bytes = ET.tostring(gdtf_root, encoding="UTF-8", xml_declaration=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("description.xml", xml_bytes)

    return path


def build_mvr(
    path: Path,
    *,
    fixtures: list[dict],
    embedded: dict[str, bytes] | None = None,
    aux_positions: dict[str, str] | None = None,
    poison: bool = False,
) -> Path:
    """Write a minimal MVR package (ZIP + GeneralSceneDescription.xml).

    ``fixtures`` is a list of dicts with keys ``name``, ``uuid``,
    ``gdtf_spec``, ``gdtf_mode``, ``address`` (absolute DMX address),
    ``position_uuid`` and ``layer``. Fixtures sharing the same ``layer``
    name are grouped under one ``<Layer>``.

    ``aux_positions`` maps a Position UUID to its name and produces
    ``<AUXData><Position uuid="..." name="..."/></AUXData>`` definitions;
    a fixture references one via a ``<Position>uuid</Position>`` child.

    ``embedded`` adds arbitrary extra ZIP entries (e.g. an orphaned
    ``Orphan@Old@r0.gdtf`` or a ``mesh1.glb``) alongside the scene XML.

    ``poison=True`` adds, to every fixture, a
    ``<CustomCommands><CustomCommand>f 0.000000</CustomCommand></CustomCommands>``
    block and a ``<Position>`` reference to a freshly generated UUID that
    has no corresponding ``AUXData`` definition (a dangling reference),
    to exercise error handling in later parser tasks.
    """
    path = Path(path)
    embedded = embedded or {}
    aux_positions = aux_positions or {}

    gsd_root = ET.Element(
        "GeneralSceneDescription", {"verMajor": "1", "verMinor": "5"}
    )
    scene_el = ET.SubElement(gsd_root, "Scene")
    layers_el = ET.SubElement(scene_el, "Layers")

    layer_child_lists = {}

    def _child_list_for_layer(layer_name: str) -> ET.Element:
        if layer_name not in layer_child_lists:
            layer_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"layer/{layer_name}"))
            layer_el = ET.SubElement(
                layers_el, "Layer", {"name": layer_name, "uuid": layer_uuid}
            )
            layer_child_lists[layer_name] = ET.SubElement(layer_el, "ChildList")
        return layer_child_lists[layer_name]

    for fixture in fixtures:
        child_list_el = _child_list_for_layer(fixture.get("layer", "Layer 1"))

        fixture_el = ET.SubElement(
            child_list_el,
            "Fixture",
            {
                "name": fixture.get("name", "Fixture"),
                "uuid": fixture.get("uuid", str(uuid.uuid4())),
            },
        )

        gdtf_spec_el = ET.SubElement(fixture_el, "GDTFSpec")
        gdtf_spec_el.text = fixture.get("gdtf_spec", "")

        gdtf_mode_el = ET.SubElement(fixture_el, "GDTFMode")
        gdtf_mode_el.text = fixture.get("gdtf_mode", "")

        addresses_el = ET.SubElement(fixture_el, "Addresses")
        address_el = ET.SubElement(addresses_el, "Address", {"break": "0"})
        address_el.text = str(fixture.get("address", 1))

        matrix_el = ET.SubElement(fixture_el, "Matrix")
        matrix_el.text = _IDENTITY_MATRIX

        if poison:
            custom_commands_el = ET.SubElement(fixture_el, "CustomCommands")
            custom_command_el = ET.SubElement(custom_commands_el, "CustomCommand")
            custom_command_el.text = "f 0.000000"

            # Dangling reference: deliberately not present in aux_positions.
            position_el = ET.SubElement(fixture_el, "Position")
            position_el.text = str(uuid.uuid4())
        else:
            position_uuid = fixture.get("position_uuid")
            if position_uuid:
                position_el = ET.SubElement(fixture_el, "Position")
                position_el.text = position_uuid

    aux_data_el = ET.SubElement(scene_el, "AUXData")
    for position_uuid, position_name in aux_positions.items():
        ET.SubElement(
            aux_data_el, "Position", {"uuid": position_uuid, "name": position_name}
        )

    xml_bytes = ET.tostring(gsd_root, encoding="UTF-8", xml_declaration=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GeneralSceneDescription.xml", xml_bytes)
        for name, content in embedded.items():
            zf.writestr(name, content)

    return path
