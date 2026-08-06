"""Tests fuer den geharteten MVR-Reader (Groessen-/Zaehl-Limits, Traversal)."""

import zipfile

from mvr_enhancer.core import mvr_reader
from mvr_enhancer.core.mvr_reader import MvrScene, read_mvr
from tests.builders import build_mvr


def test_reads_fixtures_and_embedded(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {
                "name": "Spot 1",
                "uuid": "11111111-1111-1111-1111-111111111111",
                "gdtf_spec": "Testlight@Beam@rev1.gdtf",
                "gdtf_mode": "Mode 1",
                "address": 1,
            },
            {
                "name": "Spot 2",
                "uuid": "22222222-2222-2222-2222-222222222222",
                "gdtf_spec": "Testlight@Beam@rev1.gdtf",
                "gdtf_mode": "Mode 2",
                "address": 17,
            },
        ],
        embedded={
            "Testlight@Beam@rev1.gdtf": b"fake gdtf bytes",
            "mesh1.glb": b"fake mesh bytes",
        },
    )

    scene = read_mvr(str(path))

    assert scene.xml_root is not None
    assert len(scene.fixtures) == 2

    by_name = {f.name: f for f in scene.fixtures}
    assert by_name["Spot 1"].uuid == "11111111-1111-1111-1111-111111111111"
    assert by_name["Spot 1"].gdtf_spec == "Testlight@Beam@rev1.gdtf"
    assert by_name["Spot 1"].gdtf_mode == "Mode 1"
    assert by_name["Spot 1"].dmx_address == 1
    assert "1.000000" in by_name["Spot 1"].matrix

    assert by_name["Spot 2"].dmx_address == 17
    assert by_name["Spot 2"].gdtf_mode == "Mode 2"

    assert scene.embedded_files == {
        "Testlight@Beam@rev1.gdtf": b"fake gdtf bytes",
        "mesh1.glb": b"fake mesh bytes",
    }


def test_rejects_oversized_xml(tmp_path, monkeypatch):
    """Ueber dem XML-Groessenlimit: leere Szene, keine Exception nach draussen.

    ``read_mvr`` haelt einen einheitlichen Fehlervertrag ein — jeder Defekt
    im Archiv wird geloggt und als leere ``MvrScene`` zurueckgegeben, damit
    ``api._do_load_mvr`` daraus die deutsche Fehlermeldung "keine gueltige
    MVR-Datei" bauen kann statt die Bruecke mit einer Exception zu treffen.
    """
    path = build_mvr(tmp_path / "scene.mvr", fixtures=[])

    monkeypatch.setattr(mvr_reader, "_MAX_XML_SIZE", 10)

    assert read_mvr(str(path)) == MvrScene()


def test_corrupt_zip_member_returns_empty_scene(tmp_path):
    """Gueltiger ZIP-Header, defektes Mitglied: ``zf.read()`` wirft BadZipFile.

    Die Datei laesst sich oeffnen und ihr Inhaltsverzeichnis lesen — erst das
    tatsaechliche Entpacken schlaegt fehl (CRC-Fehler). Vor dem Fix lief
    dieser Fehler ungefangen bis in die JS-Bruecke durch.
    """
    path = tmp_path / "corrupt.mvr"
    xml = (
        b"<GeneralSceneDescription verMajor='1' verMinor='5'>"
        b"<Scene><Layers/></Scene></GeneralSceneDescription>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("GeneralSceneDescription.xml", xml)

    raw = bytearray(path.read_bytes())
    offset = raw.find(b"<GeneralSceneDescription")
    assert offset != -1
    raw[offset] = ord("X")  # gleiche Laenge, kaputte CRC-32
    path.write_bytes(bytes(raw))

    with zipfile.ZipFile(path) as zf:
        assert zf.namelist() == ["GeneralSceneDescription.xml"]

    assert read_mvr(str(path)) == MvrScene()


def test_malformed_scene_xml_returns_empty_scene(tmp_path):
    """Kein XML in der GeneralSceneDescription: ET.ParseError -> leere Szene."""
    path = tmp_path / "not_xml.mvr"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GeneralSceneDescription.xml", b"<GeneralSceneDescription><Scene>")

    assert read_mvr(str(path)) == MvrScene()


def test_zip_bomb_file_count(tmp_path, monkeypatch):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[],
        embedded={"a.gdtf": b"aaa", "b.gdtf": b"bbb"},
    )

    monkeypatch.setattr(mvr_reader, "_MAX_EMBEDDED_FILE_COUNT", 1)

    scene = read_mvr(str(path))

    # Der Count-Limit-Schutz kappt eingebettete Dateien beim ersten
    # Ueberschreiten (log.warning + break) statt eine Exception zu werfen —
    # so verhaelt sich der Reader bereits im Quellprojekt.
    assert len(scene.embedded_files) == 1
    assert "a.gdtf" in scene.embedded_files


def test_bad_zip_returns_empty_scene(tmp_path):
    path = tmp_path / "not_a_zip.mvr"
    path.write_bytes(b"this is definitely not a zip file")

    scene = read_mvr(str(path))

    assert scene == MvrScene()


def test_path_traversal_entries_skipped(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[],
        embedded={
            "..\\evil.txt": b"evil-content",
            "good.gdtf": b"good-content",
        },
    )

    scene = read_mvr(str(path))

    assert "good.gdtf" in scene.embedded_files
    assert all(
        ".." not in name.replace("\\", "/").split("/")
        for name in scene.embedded_files
    )


def test_percent_encoded_traversal_entries_skipped(tmp_path):
    """Percent-encoded traversal must be rejected too.

    The raw ZIP entry name is harmless-looking, but ``enricher._clean_gdtf_name``
    URL-decodes it before re-emitting it into the exported archive — so the
    reader has to decode (repeatedly, until stable) BEFORE the traversal check,
    or a ``%2E%2E%2F``-encoded entry sneaks a real ``../`` into the export.
    """
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[],
        embedded={
            "%2E%2E%2F%2E%2E%2Fevil.gdtf": b"evil-content",
            "%252E%252E%252Fdouble.gdtf": b"double-encoded-evil",
            "sub%2F%2E%2E%2F%2E%2E%2Fescape.gdtf": b"nested-evil",
            "%2FC%3A%2Fabsolute.gdtf": b"absolute-evil",
            "good.gdtf": b"good-content",
        },
    )

    scene = read_mvr(str(path))

    assert scene.embedded_files == {"good.gdtf": b"good-content"}


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
