"""Tests fuer den read-only VectorWatch-Abgleich (core/vectorwatch.py + api-Hook).

Der Provider liest eine (hier in ``tmp_path`` nachgebaute) VectorWatch-
Installation: ``config.json``, ``projects/*.json`` und ``gdtf_library/``
mit ``index.json`` bzw. Fixture-Caches. Die Api-Tests laufen wie ueberall
mit ``Api(sync=True)``; der Provider wird per Instanz-Attribut
``api._vectorwatch`` auf die Fake-Installation umgebogen.
"""

import json
import os

from mvr_enhancer.api import Api
from mvr_enhancer.core.vectorwatch import VectorWatchProvider
from mvr_enhancer.settings import Settings
from tests.builders import build_gdtf, build_mvr

_MODES_ENTRY = [
    {"name": "Mode 1", "channel_count": 16},
    {"name": "Mode 2", "channel_count": 32},
]


def _make_vw_install(
    tmp_path,
    *,
    project_name="Sommerfest 2026",
    snapshot_names=("Spot A",),
    overrides=None,
    mode_overrides=None,
    write_index=True,
    config=None,
):
    """Baut eine minimale Fake-VectorWatch-Installation unter ``tmp_path``."""
    vw_dir = tmp_path / "VectorWatch"
    projects_dir = vw_dir / "projects"
    library_dir = vw_dir / "gdtf_library"
    projects_dir.mkdir(parents=True)
    library_dir.mkdir()

    build_gdtf(
        library_dir / "Testlight@Spot A@rev1.gdtf",
        manufacturer="Testlight",
        name="Spot A",
    )
    entry = {
        "manufacturer": "Testlight",
        "name": "Spot A",
        "revision": "rev1",
        "modes": _MODES_ENTRY,
    }
    if write_index:
        (library_dir / "index.json").write_text(
            json.dumps({"fixtures": [entry]}), encoding="utf-8"
        )
    else:
        (library_dir / "Spot A.json").write_text(json.dumps(entry), encoding="utf-8")

    _write_project(
        projects_dir,
        project_name,
        snapshot_names=snapshot_names,
        overrides=overrides,
        mode_overrides=mode_overrides,
    )
    if config is not None:
        (vw_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return vw_dir


def _write_project(
    projects_dir, project_name, *, snapshot_names=(), overrides=None, mode_overrides=None
):
    project = {
        "project_name": project_name,
        "dmx_gdtf_overrides": overrides or {},
        "dmx_mode_overrides": mode_overrides or {},
        "snapshot": {"fixtures": [{"name": n} for n in snapshot_names]},
    }
    path = projects_dir / f"{project_name}.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def _snapshot_tree(root) -> set[str]:
    """Alle Pfade unter ``root`` (fuer den Nachweis: Provider schreibt nie)."""
    result = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            result.add(os.path.join(dirpath, name))
    return result


# ──── Provider: Projekt-Matching & Status ────


def test_matched_with_override(tmp_path):
    vw_dir = _make_vw_install(
        tmp_path,
        snapshot_names=("Spot A", "Verteiler 1"),
        overrides={"Verteiler 1": "Spot A"},
        mode_overrides={"Verteiler 1": "Mode 2"},
    )
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A", "Verteiler 1"])

    assert result.status == "matched"
    assert result.project_name == "Sommerfest 2026"
    assert result.coverage == 1.0
    by_name = {a.type_name: a for a in result.assignments}
    # "Verteiler 1" matcht nur ueber den Override (Score gegen "Spot A" = 0).
    verteiler = by_name["Verteiler 1"]
    assert verteiler.source == "override"
    assert verteiler.gdtf_name == "Spot A"
    assert verteiler.gdtf_file.endswith("Testlight@Spot A@rev1.gdtf")
    assert os.path.isfile(verteiler.gdtf_file)
    assert verteiler.mode == "Mode 2"


def test_auto_match_without_override(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert result.status == "matched"
    assert len(result.assignments) == 1
    assert result.assignments[0].source == "auto"
    assert result.assignments[0].gdtf_name == "Spot A"
    assert result.assignments[0].mode == ""


def test_empty_override_means_none(tmp_path):
    vw_dir = _make_vw_install(tmp_path, overrides={"Spot A": ""})
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert result.status == "matched"
    assert result.assignments[0].source == "none"
    assert result.assignments[0].gdtf_name == ""
    assert result.assignments[0].gdtf_file == ""


def test_no_matching_project(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Anderes Event.mvr", ["Spot A"])

    assert result.status == "no_project"
    assert result.assignments == []


def test_low_coverage_rejects_name_coincidence(tmp_path):
    vw_dir = _make_vw_install(tmp_path, snapshot_names=("Wash B",))
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments(
        "Sommerfest 2026.mvr", ["Spot A", "Verteiler 1", "Par 3"]
    )

    assert result.status == "low_coverage"
    assert result.project_name == "Sommerfest 2026"
    assert result.coverage == 0.0
    assert result.assignments == []


def test_missing_snapshot_counts_as_low_coverage(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    project_path = vw_dir / "projects" / "Sommerfest 2026.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    del project["snapshot"]
    project_path.write_text(json.dumps(project), encoding="utf-8")
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert result.status == "low_coverage"


def test_fuzzy_project_match_prefers_newest(tmp_path):
    vw_dir = _make_vw_install(tmp_path, project_name="Sommerfest")
    projects_dir = vw_dir / "projects"
    newer = _write_project(
        projects_dir, "Sommerfest 2026", snapshot_names=("Spot A",)
    )
    os.utime(projects_dir / "Sommerfest.json", (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026 v3.mvr", ["Spot A"])

    assert result.status == "matched"
    assert result.project_name == "Sommerfest 2026"


def test_broken_project_json_falls_back_to_next_candidate(tmp_path):
    vw_dir = _make_vw_install(tmp_path, project_name="Sommerfest 2026")
    projects_dir = vw_dir / "projects"
    broken = projects_dir / "Sommerfest 2026 kaputt.json"
    broken.write_text("{nicht json", encoding="utf-8")
    os.utime(projects_dir / "Sommerfest 2026.json", (1_000_000, 1_000_000))
    os.utime(broken, (2_000_000, 2_000_000))
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert result.status == "matched"
    assert result.project_name == "Sommerfest 2026"


def test_unavailable_without_installation(tmp_path):
    provider = VectorWatchProvider(str(tmp_path / "gibt-es-nicht"))

    assert provider.is_available() is False
    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])
    assert result.status == "unavailable"


def test_library_fallback_without_index_json(tmp_path):
    vw_dir = _make_vw_install(tmp_path, write_index=False)
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert result.status == "matched"
    assert result.assignments[0].gdtf_name == "Spot A"


def test_custom_dirs_from_vw_config(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    custom_projects = tmp_path / "custom_projects"
    custom_projects.mkdir()
    _write_project(custom_projects, "Winterfest", snapshot_names=("Spot A",))
    (vw_dir / "config.json").write_text(
        json.dumps({"projects_dir": str(custom_projects)}), encoding="utf-8"
    )
    provider = VectorWatchProvider(str(vw_dir))

    result = provider.get_assignments("Winterfest.mvr", ["Spot A"])

    assert result.status == "matched"
    assert result.project_name == "Winterfest"


def test_provider_never_writes_into_vectorwatch_dirs(tmp_path):
    vw_dir = _make_vw_install(tmp_path, write_index=False)
    before = _snapshot_tree(vw_dir)
    provider = VectorWatchProvider(str(vw_dir))

    provider.get_assignments("Sommerfest 2026.mvr", ["Spot A"])

    assert _snapshot_tree(vw_dir) == before


# ──── Api-Integration (sync=True) ────


def _make_api_with_vw(tmp_path, vw_dir, *, library_dir=None, sync_enabled=True) -> Api:
    base_dir = tmp_path / "appdata"
    settings = Settings.load(str(base_dir))
    if library_dir is not None:
        library_dir.mkdir(parents=True, exist_ok=True)
        settings.gdtf_library_dir = str(library_dir)
    settings.vectorwatch_sync = sync_enabled
    settings.save()
    api = Api(sync=True, base_dir=str(base_dir))
    api._vectorwatch = VectorWatchProvider(str(vw_dir))
    return api


def _build_scene(tmp_path):
    return build_mvr(
        tmp_path / "Sommerfest 2026.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )


def test_load_mvr_applies_vectorwatch_matching(tmp_path):
    vw_dir = _make_vw_install(tmp_path, mode_overrides={"Spot A": "Mode 2"})
    mvr_path = _build_scene(tmp_path)
    library_dir = tmp_path / "enhancer_library"
    api = _make_api_with_vw(tmp_path, vw_dir, library_dir=library_dir)

    result = api.load_mvr(str(mvr_path))

    assert result["ok"] is True
    state = api.get_state()["data"]
    vw_state = state["vectorwatch"]
    assert vw_state["enabled"] is True
    assert vw_state["status"] == "matched"
    assert vw_state["project_name"] == "Sommerfest 2026"
    assert vw_state["applied"] == 1
    assert vw_state["total"] == 1

    spot = state["types"][0]
    assert spot["assignment"]["source"] == "vectorwatch"
    assert spot["assignment"]["gdtf_name"] == "Spot A"
    assert spot["assignment"]["mode_name"] == "Mode 2"
    assert spot["assignment"]["mode_is_fallback"] is False

    # Die GDTF wurde aus der VectorWatch-Bibliothek in die eigene kopiert.
    assert (library_dir / "Testlight@Spot A@rev1.gdtf").is_file()


def test_load_mvr_vw_none_leaves_type_unassigned(tmp_path):
    vw_dir = _make_vw_install(tmp_path, overrides={"Spot A": ""})
    mvr_path = _build_scene(tmp_path)
    library_dir = tmp_path / "enhancer_library"
    # Lokale Bibliothek enthaelt einen perfekten Treffer — ohne den
    # VectorWatch-"kein Match gewuenscht"-Override wuerde er zugeordnet.
    build_gdtf(library_dir / "Testlight@Spot A@rev1.gdtf", name="Spot A")
    api = _make_api_with_vw(tmp_path, vw_dir, library_dir=library_dir)

    api.load_mvr(str(mvr_path))

    state = api.get_state()["data"]
    assert state["vectorwatch"]["status"] == "matched"
    assert state["vectorwatch"]["applied"] == 0
    spot = state["types"][0]
    assert spot["assignment"]["gdtf_name"] is None
    assert spot["candidates"], "Vorschlaege muessen sichtbar bleiben"


def test_load_mvr_with_sync_disabled_keeps_local_matching(tmp_path):
    vw_dir = _make_vw_install(tmp_path, overrides={"Spot A": ""})
    mvr_path = _build_scene(tmp_path)
    library_dir = tmp_path / "enhancer_library"
    build_gdtf(library_dir / "Testlight@Spot A@rev1.gdtf", name="Spot A")
    api = _make_api_with_vw(tmp_path, vw_dir, library_dir=library_dir, sync_enabled=False)

    api.load_mvr(str(mvr_path))

    state = api.get_state()["data"]
    assert state["vectorwatch"]["enabled"] is False
    assert state["vectorwatch"]["status"] == "idle"
    spot = state["types"][0]
    assert spot["assignment"]["source"] == "library"
    assert spot["assignment"]["gdtf_name"] == "Spot A"


def test_load_mvr_without_vw_installation(tmp_path):
    mvr_path = _build_scene(tmp_path)
    library_dir = tmp_path / "enhancer_library"
    build_gdtf(library_dir / "Testlight@Spot A@rev1.gdtf", name="Spot A")
    api = _make_api_with_vw(tmp_path, tmp_path / "gibt-es-nicht", library_dir=library_dir)

    api.load_mvr(str(mvr_path))

    state = api.get_state()["data"]
    assert state["vectorwatch"]["status"] == "unavailable"
    assert state["types"][0]["assignment"]["source"] == "library"


def test_load_mvr_without_library_dir_reports_library_missing(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    mvr_path = _build_scene(tmp_path)
    api = _make_api_with_vw(tmp_path, vw_dir, library_dir=None)

    api.load_mvr(str(mvr_path))

    state = api.get_state()["data"]
    assert state["vectorwatch"]["status"] == "library_missing"
    assert state["types"][0]["assignment"]["gdtf_name"] is None


def test_set_vectorwatch_sync_persists(tmp_path):
    vw_dir = _make_vw_install(tmp_path)
    api = _make_api_with_vw(tmp_path, vw_dir)

    result = api.set_vectorwatch_sync(False)

    assert result["ok"] is True
    assert result["data"]["vectorwatch"]["enabled"] is False
    reloaded = Settings.load(str(tmp_path / "appdata"))
    assert reloaded.vectorwatch_sync is False
