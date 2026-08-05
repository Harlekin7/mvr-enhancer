"""Tests fuer analysis.py (Typ-Aggregation, Positionen, Stats, Kollisionen)."""

from mvr_enhancer.core.analysis import (
    aggregate_fixture_types,
    compute_stats,
    detect_address_collisions,
    parse_position_names,
)
from mvr_enhancer.core.models import Assignment
from mvr_enhancer.core.mvr_reader import read_mvr
from tests.builders import build_mvr


def test_aggregate_groups_by_name(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2},
            {"name": "Spot A", "uuid": "33333333-3333-3333-3333-333333333333",
             "address": 3},
            {"name": "Wash B", "uuid": "44444444-4444-4444-4444-444444444444",
             "address": 4},
            {"name": "Wash B", "uuid": "55555555-5555-5555-5555-555555555555",
             "address": 5},
        ],
    )

    scene = read_mvr(str(path))
    types = aggregate_fixture_types(scene)

    assert len(types) == 2
    counts = {t.name: t.count for t in types}
    assert counts["Spot A"] == 3
    assert counts["Wash B"] == 2


def test_positions_from_auxdata(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "position_uuid": "aaaaaaaa-0000-0000-0000-000000000000"},
        ],
        aux_positions={"aaaaaaaa-0000-0000-0000-000000000000": "Truss 1"},
    )

    scene = read_mvr(str(path))

    position_map = parse_position_names(scene)
    assert position_map == {"aaaaaaaa-0000-0000-0000-000000000000": "Truss 1"}

    types = aggregate_fixture_types(scene)
    assert len(types) == 1
    assert types[0].positions == ["Truss 1"]
    assert "Truss 1" in types[0].meta_line


def test_position_fallback_layer(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "layer": "Traverse 1"},
        ],
    )

    scene = read_mvr(str(path))
    assert scene.aux_data is None

    types = aggregate_fixture_types(scene)
    assert len(types) == 1
    assert types[0].positions == ["Traverse 1"]


def test_stats_counts(tmp_path):
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": 1, "position_uuid": "aaaaaaaa-0000-0000-0000-000000000000"},
            {"name": "Wash B", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": 2, "position_uuid": "bbbbbbbb-0000-0000-0000-000000000000"},
        ],
        aux_positions={
            "aaaaaaaa-0000-0000-0000-000000000000": "Truss 1",
            "bbbbbbbb-0000-0000-0000-000000000000": "Truss 2",
        },
        embedded={
            "Testlight@Beam@rev1.gdtf": b"fake gdtf bytes",
            "mesh1.glb": b"fake mesh bytes",
            "mesh2.GLTF": b"fake mesh bytes 2",
            "readme.txt": b"not a mesh",
        },
    )

    scene = read_mvr(str(path))
    types = aggregate_fixture_types(scene)
    stats = compute_stats(scene, types)

    assert stats.fixtures == 2
    assert stats.fixture_types == 2
    assert stats.meshes == 2
    assert stats.positions == 2


def test_collision_detected(tmp_path):
    # Universe 4, channels 12.. — two overlapping fixtures of the same type.
    base = (4 - 1) * 512
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Overlap Light", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": base + 12},
            {"name": "Overlap Light", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": base + 14},
        ],
    )

    scene = read_mvr(str(path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {key: Assignment(gdtf_name="Overlap.gdtf", mode_name="Mode 1")}
    footprints = {key: 4}

    warnings = detect_address_collisions(scene, types, assignments, footprints)

    assert len(warnings) == 1
    assert warnings[0].universe == 4
    assert set(warnings[0].fixture_names) == {"Overlap Light"}
    assert len(warnings[0].fixture_names) == 2


def test_no_collision_when_removed(tmp_path):
    base = (4 - 1) * 512
    path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Overlap Light", "uuid": "11111111-1111-1111-1111-111111111111",
             "address": base + 12},
            {"name": "Overlap Light", "uuid": "22222222-2222-2222-2222-222222222222",
             "address": base + 14},
        ],
    )

    scene = read_mvr(str(path))
    types = aggregate_fixture_types(scene)
    key = types[0].key
    assignments = {
        key: Assignment(gdtf_name="Overlap.gdtf", mode_name="Mode 1", removed=True),
    }
    footprints = {key: 4}

    warnings = detect_address_collisions(scene, types, assignments, footprints)

    assert warnings == []
