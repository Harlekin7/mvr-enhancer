"""Generate demo/ fixture data for manual, end-to-end verification of the UI.

Produces (all under ``demo/``, next to the repo root):

- ``demo/gdtf-library/*.gdtf`` -- 3 minimal GDTF fixtures, built with
  ``tests.builders.build_gdtf``, matching the fixture types used below (and
  echoing the design handoff's mock table): Robe MegaPointe, Martin MAC
  Aura PXL, Cameo Zenit W600.
- ``demo/quelle.mvr`` -- a minimal MVR built with ``tests.builders.build_mvr``,
  containing:

  - 3 fixture types that match the library GDTFs above. Their existing
    ``<GDTFMode>`` is left blank, so the app resolves a fallback mode
    (``modes[0]``) for all of them -- this exercises the amber
    "Modus-Fallback" warning across the whole table.
  - 1 fixture type with no library match at all ("Acme Blaster 9000") --
    exercises the "kein Treffer in der Bibliothek" / "Im Share suchen" path.
  - fixture positions via ``<AUXData><Position>`` (``aux_positions``), so
    the "Nach Position gruppieren" checkbox and the table's meta-line
    position text have real data to group by.
  - one deliberate DMX address overlap between a Robe MegaPointe and a
    Martin MAC Aura PXL fixture in the same universe -- exercises the red
    "Adress-Kollision" warning.
  - an orphaned embedded GDTF file (never referenced by any assignment)
    and a fake mesh asset -- exercise the cleanup-preview orphan count and
    the "3D-Meshes" stat respectively.

  ``build_mvr``'s ``poison`` flag is all-or-nothing across *every* fixture
  in a single call (it has no per-fixture override), so it can't produce
  one poisoned fixture alongside the matching ones above without poisoning
  everything. This script therefore builds the base scene via
  ``build_mvr`` as usual and then, as a small documented post-processing
  step (``_add_poison_fixture``), appends one additional poisoned
  ``<Fixture>`` element -- a ``<CustomCommands>`` block plus a dangling
  ``<Position>`` reference with no matching ``<AUXData>`` entry, mirroring
  exactly what ``build_mvr(poison=True)`` writes per fixture -- directly
  into the scene XML before rewriting the archive.

Usage::

    .venv/Scripts/python tools/make_demo_data.py [--out demo]

Then run the app, point the GDTF library directory at
``demo/gdtf-library`` and load ``demo/quelle.mvr`` to exercise the full
load -> match -> export pipeline with real data.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.builders import build_gdtf, build_mvr  # noqa: E402

_IDENTITY_MATRIX = (
    "{1.000000,0.000000,0.000000,0.000000}"
    "{0.000000,1.000000,0.000000,0.000000}"
    "{0.000000,0.000000,1.000000,0.000000}"
    "{0.000000,0.000000,0.000000,1.000000}"
)


def _uuid(seed: str) -> str:
    """Deterministic UUID from a seed string, so re-runs produce stable output."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, seed))


def build_library(library_dir: Path) -> None:
    """Writes the 3 demo GDTFs that the demo MVR's fixture types match against."""
    library_dir.mkdir(parents=True, exist_ok=True)
    build_gdtf(
        library_dir / "Robe@MegaPointe@rev1.gdtf",
        manufacturer="Robe",
        name="MegaPointe",
        revision="rev1",
        modes=(("Mode 1 Standard", 39), ("Mode 2 Basic", 27)),
    )
    build_gdtf(
        library_dir / "Martin@MAC_Aura_PXL@rev1.gdtf",
        manufacturer="Martin",
        name="MAC Aura PXL",
        revision="rev1",
        modes=(("P1 Basic", 14), ("P2 Extended", 23)),
    )
    build_gdtf(
        library_dir / "Cameo@Zenit_W600@rev1.gdtf",
        manufacturer="Cameo",
        name="Zenit W600",
        revision="rev1",
        modes=(("Mode 1", 10), ("Mode 2", 6)),
    )
    print(f"wrote 3 GDTFs to {library_dir}")


def _add_poison_fixture(mvr_path: Path) -> None:
    """Appends one poisoned ``<Fixture>`` to an already-written MVR archive.

    Mirrors exactly what ``tests.builders.build_mvr(poison=True)`` writes per
    fixture (a ``<CustomCommands>`` block + a dangling ``<Position>``
    reference with no corresponding ``<AUXData>`` entry) -- done as a
    post-processing step since ``poison`` is otherwise all-or-nothing across
    an entire ``build_mvr`` call and would have poisoned every other fixture
    in the scene too.
    """
    with zipfile.ZipFile(mvr_path, "r") as zf:
        xml_data = zf.read("GeneralSceneDescription.xml")
        other_files = {
            name: zf.read(name) for name in zf.namelist() if name != "GeneralSceneDescription.xml"
        }

    root = ET.fromstring(xml_data)
    child_list = root.find("./Scene/Layers/Layer/ChildList")
    if child_list is None:
        raise RuntimeError("expected <Layer><ChildList> not found in generated MVR")

    fixture_el = ET.SubElement(
        child_list,
        "Fixture",
        {"name": "Poison Fixture", "uuid": _uuid("poison-fixture")},
    )
    ET.SubElement(fixture_el, "GDTFSpec").text = ""
    ET.SubElement(fixture_el, "GDTFMode").text = ""
    addresses_el = ET.SubElement(fixture_el, "Addresses")
    ET.SubElement(addresses_el, "Address", {"break": "0"}).text = "600"
    ET.SubElement(fixture_el, "Matrix").text = _IDENTITY_MATRIX
    custom_commands_el = ET.SubElement(fixture_el, "CustomCommands")
    ET.SubElement(custom_commands_el, "CustomCommand").text = "f 0.000000"
    # Dangling reference: deliberately no matching <AUXData><Position>.
    ET.SubElement(fixture_el, "Position").text = _uuid("poison-dangling-position")

    new_xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    with zipfile.ZipFile(mvr_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GeneralSceneDescription.xml", new_xml)
        for name, data in other_files.items():
            zf.writestr(name, data)


def build_scene(out_dir: Path) -> Path:
    """Writes ``demo/quelle.mvr`` -- see module docstring for its contents."""
    pos_traverse1 = _uuid("pos-traverse-1")
    pos_traverse2 = _uuid("pos-traverse-2")
    pos_foh = _uuid("pos-foh")
    pos_boden = _uuid("pos-boden")

    fixtures = []

    # 4x Robe MegaPointe -- matches the library. GDTFMode left blank so the
    # app resolves modes[0] ("Mode 1 Standard", 39ch) as a fallback. The
    # last one (addr 200) deliberately overlaps a Martin fixture below.
    for i, addr in enumerate((1, 41, 81, 200)):
        fixtures.append({
            "name": "Robe MegaPointe",
            "uuid": _uuid(f"robe-{i}"),
            "gdtf_spec": "",
            "gdtf_mode": "",
            "address": addr,
            "position_uuid": pos_traverse1,
            "layer": "Traverse 1",
        })

    # 3x Martin MAC Aura PXL -- matches the library, fallback mode "P1
    # Basic" (14ch). addr 210 lands inside the Robe fixture's 200..238
    # footprint above -> exercises the red address-collision warning.
    for i, addr in enumerate((210, 300, 314)):
        fixtures.append({
            "name": "Martin MAC Aura PXL",
            "uuid": _uuid(f"martin-{i}"),
            "gdtf_spec": "",
            "gdtf_mode": "",
            "address": addr,
            "position_uuid": pos_traverse2,
            "layer": "Traverse 2",
        })

    # 2x Cameo Zenit W600 -- matches the library, fallback mode "Mode 1" (10ch).
    for i, addr in enumerate((400, 415)):
        fixtures.append({
            "name": "Cameo Zenit W600",
            "uuid": _uuid(f"cameo-{i}"),
            "gdtf_spec": "",
            "gdtf_mode": "",
            "address": addr,
            "position_uuid": pos_foh,
            "layer": "FOH",
        })

    # 2x Acme Blaster 9000 -- no library match at all (score below the 0.3
    # suggestion threshold) -> "kein Treffer in der Bibliothek" UI path.
    for i, addr in enumerate((500, 510)):
        fixtures.append({
            "name": "Acme Blaster 9000",
            "uuid": _uuid(f"acme-{i}"),
            "gdtf_spec": "",
            "gdtf_mode": "",
            "address": addr,
            "position_uuid": pos_boden,
            "layer": "Boden",
        })

    mvr_path = out_dir / "quelle.mvr"
    build_mvr(
        mvr_path,
        fixtures=fixtures,
        embedded={
            "Orphan@Old@r0.gdtf": b"not a real gdtf -- only used to exercise orphan detection",
            "mesh1.glb": b"not a real mesh -- only used to exercise the mesh-count stat",
        },
        aux_positions={
            pos_traverse1: "Traverse 1",
            pos_traverse2: "Traverse 2",
            pos_foh: "FOH",
            pos_boden: "Boden",
        },
    )
    _add_poison_fixture(mvr_path)
    print(f"wrote {mvr_path} (11 fixtures + 1 poison fixture, 1 orphaned GDTF, 1 mesh)")
    return mvr_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demo", help="output directory (default: demo/)")
    args = parser.parse_args()

    out_dir = REPO_ROOT / args.out
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    build_library(out_dir / "gdtf-library")
    build_scene(out_dir)

    print()
    print("Zum Testen:")
    print(f"  1. App starten, Bibliotheksordner auf {out_dir / 'gdtf-library'} setzen")
    print(f"  2. {out_dir / 'quelle.mvr'} laden")


if __name__ == "__main__":
    main()
