"""Tests fuer api.py (JS<->Python-Bruecke, Zustand, Export-Flow).

Alle Tests verwenden ``Api(sync=True)`` (Testmodus): lange Operationen
laufen synchron auf dem aufrufenden Thread und Events landen in
``api.events`` statt in ``window.evaluate_js``. Dialoge/``window`` werden
ueber ``FakeWindow`` gemockt; das GDTF-Share-Netzwerk wird wie in
``tests/test_share.py`` durch Monkeypatching von ``GdtfShareClient._request``
ersetzt.
"""

import json
import os

from mvr_enhancer.api import Api
from mvr_enhancer.settings import Settings
from tests.builders import build_gdtf, build_mvr


class FakeWindow:
    """Ersetzt das echte pywebview-Fenster in Tests."""

    def __init__(self, dialog_paths=None):
        self.dialog_paths = dialog_paths
        self.titles: list[str] = []
        self.evaluated: list[str] = []

    def create_file_dialog(self, dialog_type=None, directory="", allow_multiple=False,
                            save_filename="", file_types=()):
        return self.dialog_paths

    def set_title(self, title):
        self.titles.append(title)

    def evaluate_js(self, js):
        self.evaluated.append(js)


def _setup_library(tmp_path, modes=(("Mode 1", 16), ("Mode 2", 32))):
    library_dir = tmp_path / "library"
    build_gdtf(
        library_dir / "Testlight@Spot A@rev1.gdtf",
        manufacturer="Testlight", name="Spot A", modes=modes,
    )
    return library_dir


def _make_api(tmp_path, library_dir=None) -> Api:
    base_dir = tmp_path / "appdata"
    if library_dir is not None:
        settings = Settings.load(str(base_dir))
        settings.gdtf_library_dir = str(library_dir)
        settings.save()
    return Api(sync=True, base_dir=str(base_dir))


def _types_by_name(state: dict) -> dict:
    return {t["name"]: t for t in state["types"]}


# ──── test_load_mvr_populates_state ────


def test_load_mvr_populates_state(tmp_path):
    library_dir = _setup_library(tmp_path)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222", "address": 100},
            {"name": "Verteiler 1", "uuid": "33333333-3333-3333-3333-333333333333", "address": 200},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    result = api.load_mvr(str(mvr_path))

    assert result["ok"] is True
    state = api.get_state()["data"]

    assert state["mvr_loaded"] is True
    assert state["file_meta"]["name"] == "scene.mvr"
    assert state["file_meta"]["path"] == str(mvr_path)
    assert state["file_meta"]["size_mb"] >= 0

    types = _types_by_name(state)
    assert set(types) == {"Spot A", "Verteiler 1"}

    spot = types["Spot A"]
    assert spot["candidates"][0]["gdtf_name"] == "Spot A"
    assert spot["candidates"][0]["score"] == 1.0
    assert spot["assignment"]["gdtf_name"] == "Spot A"
    # existing_mode is empty (builder default) -> substring match fails -> modes[0] fallback.
    assert spot["assignment"]["mode_name"] == "Mode 1"
    assert spot["assignment"]["mode_is_fallback"] is True
    assert spot["assignment"]["removed"] is False

    verteiler = types["Verteiler 1"]
    assert verteiler["candidates"] == []
    assert verteiler["assignment"]["gdtf_name"] is None
    assert verteiler["assignment"]["removed"] is False

    assert state["assigned_count"] == 1
    assert state["open_count"] == 1

    # Sync mode: a "state" event must have been recorded instead of evaluate_js.
    assert any(e["type"] == "state" for e in api.events)


# ──── test_set_gdtf_and_mode ────


def test_set_gdtf_and_mode(tmp_path):
    library_dir = _setup_library(tmp_path)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Mystery Beam", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    api.load_mvr(str(mvr_path))

    state = api.get_state()["data"]
    mystery = _types_by_name(state)["Mystery Beam"]
    assert mystery["assignment"]["gdtf_name"] is None
    key = mystery["key"]

    result = api.set_gdtf(key, "Spot A")
    assert result["ok"] is True
    state = result["data"]
    mystery = _types_by_name(state)["Mystery Beam"]
    assert mystery["assignment"]["gdtf_name"] == "Spot A"
    assert mystery["assignment"]["mode_name"] == "Mode 1"
    assert mystery["assignment"]["mode_is_fallback"] is True
    assert state["assigned_count"] == 1
    assert state["open_count"] == 0

    result = api.set_mode(key, "Mode 2")
    assert result["ok"] is True
    mystery = _types_by_name(result["data"])["Mystery Beam"]
    assert mystery["assignment"]["mode_name"] == "Mode 2"
    assert mystery["assignment"]["mode_is_fallback"] is False


# ──── test_set_removed_affects_cleanup_preview ────


def test_set_removed_affects_cleanup_preview(tmp_path):
    library_dir = _setup_library(tmp_path)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222", "address": 100},
            {"name": "Wash B", "uuid": "33333333-3333-3333-3333-333333333333", "address": 200},
            {"name": "Wash B", "uuid": "44444444-4444-4444-4444-444444444444", "address": 220},
            {"name": "Wash B", "uuid": "55555555-5555-5555-5555-555555555555", "address": 240},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    api.load_mvr(str(mvr_path))
    state = api.get_state()["data"]
    spot_key = _types_by_name(state)["Spot A"]["key"]

    baseline = api.prepare_export()["data"]
    preview = baseline["warnings"]["cleanup_preview"]
    assert preview["removed_fixture_count"] == 3  # 3x unmatched "Wash B"
    assert preview["open_type_names"] == ["Wash B"]

    api.set_removed(spot_key, True)
    updated = api.prepare_export()["data"]
    updated_preview = updated["warnings"]["cleanup_preview"]
    assert updated_preview["removed_fixture_count"] == 5  # + 2x now-removed "Spot A"
    assert updated_preview["open_type_names"] == ["Wash B"]  # removed type is not "open"


# ──── test_prepare_export_warnings ────


def test_prepare_export_warnings(tmp_path):
    library_dir = _setup_library(tmp_path)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            # Mode 1 has a 16-channel footprint: [1,16] and [10,25] overlap -> one collision.
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222", "address": 10},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    api.load_mvr(str(mvr_path))

    result = api.prepare_export()
    assert result["ok"] is True
    warnings = result["data"]["warnings"]

    assert len(warnings["fallbacks"]) == 1
    fallback = warnings["fallbacks"][0]
    assert fallback["type_name"] == "Spot A"
    assert fallback["count"] == 2
    assert fallback["gdtf_name"] == "Spot A"
    assert fallback["mode_name"] == "Mode 1"

    assert len(warnings["collisions"]) == 1
    collision = warnings["collisions"][0]
    assert collision["universe"] == 1


# ──── test_run_export_writes_file_and_report ────


def test_run_export_writes_file_and_report(tmp_path):
    library_dir = _setup_library(tmp_path)

    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
            {"name": "Spot A", "uuid": "22222222-2222-2222-2222-222222222222", "address": 100},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    api.load_mvr(str(mvr_path))

    export_path = tmp_path / "out" / "scene_MA3.mvr"
    result = api.run_export(str(export_path))

    assert result["ok"] is True
    assert os.path.isfile(export_path)
    assert result["data"]["report"]["matched_fixtures"] == 2
    assert result["data"]["path"] == str(export_path)
    assert result["data"]["size_mb"] >= 0
    assert "time_str" in result["data"]

    state = api.get_state()["data"]
    assert state["export"]["done"] is True
    assert state["export"]["path"] == str(export_path)


# ──── test_recent_persisted ────


def test_recent_persisted(tmp_path):
    library_dir = _setup_library(tmp_path)
    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    base_dir = tmp_path / "appdata"
    settings = Settings.load(str(base_dir))
    settings.gdtf_library_dir = str(library_dir)
    settings.save()

    api = Api(sync=True, base_dir=str(base_dir))
    result = api.load_mvr(str(mvr_path))
    assert result["ok"] is True

    reloaded = Settings.load(str(base_dir))
    assert len(reloaded.recent_files) == 1
    assert reloaded.recent_files[0]["path"] == str(mvr_path)

    state = api.get_state()["data"]
    assert state["recent"][0]["path"] == str(mvr_path)
    assert state["recent"][0]["name"] == "scene.mvr"


# ──── test_share_login_updates_state ────


def test_share_login_updates_state(tmp_path, monkeypatch):
    api = _make_api(tmp_path)

    def fake_request(method, slug, params=None, data=None):
        assert slug == "login.php"
        assert data == {"user": "alice", "password": "secret"}
        return 200, json.dumps({"result": True}).encode()

    monkeypatch.setattr(api._share, "_request", fake_request)

    result = api.share_login("alice", "secret", True)
    assert result["ok"] is True

    state = api.get_state()["data"]
    assert state["share"]["logged_in"] is True
    assert state["share"]["user"] == "alice"

    reloaded = Settings.load(api._settings.base_dir)
    assert reloaded.share_user == "alice"
    assert reloaded.share_password_enc.startswith("dpapi:")

    assert any(e["type"] == "state" for e in api.events)


# ──── Bonus coverage: dialogs, error paths, simple methods ────


def test_choose_mvr_uses_dialog_and_loads(tmp_path):
    library_dir = _setup_library(tmp_path)
    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    window = FakeWindow(dialog_paths=[str(mvr_path)])
    api.set_window(window)

    result = api.choose_mvr()
    assert result["ok"] is True
    assert result["data"]["mvr_loaded"] is True
    assert window.titles[-1] == f"Groh·PA MVR Export — {mvr_path.name}"


def test_choose_mvr_cancelled_dialog(tmp_path):
    api = _make_api(tmp_path)
    window = FakeWindow(dialog_paths=None)
    api.set_window(window)

    result = api.choose_mvr()
    assert result["ok"] is True
    assert result["data"] == {"cancelled": True}


def test_rescan_library_refreshes_open_candidates(tmp_path):
    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    api = _make_api(tmp_path)  # no library yet -> stays open, no candidates
    api.load_mvr(str(mvr_path))
    state = api.get_state()["data"]
    assert state["types"][0]["candidates"] == []

    library_dir = _setup_library(tmp_path)
    api._settings.gdtf_library_dir = str(library_dir)
    api._settings.save()

    result = api.rescan_library()
    assert result["ok"] is True
    state = result["data"]
    assert state["library"]["count"] == 1
    spot = state["types"][0]
    assert spot["candidates"][0]["gdtf_name"] == "Spot A"
    # rescan only refreshes candidates, it does not auto-assign.
    assert spot["assignment"]["gdtf_name"] is None


def test_remove_mvr_resets_state(tmp_path):
    library_dir = _setup_library(tmp_path)
    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    window = FakeWindow()
    api.set_window(window)
    api.load_mvr(str(mvr_path))

    result = api.remove_mvr()
    assert result["ok"] is True
    state = result["data"]
    assert state["mvr_loaded"] is False
    assert state["types"] == []
    assert state["file_meta"] == {}
    assert window.titles[-1] == "Groh·PA MVR Export"


def test_reset_export_clears_done(tmp_path):
    library_dir = _setup_library(tmp_path)
    mvr_path = build_mvr(
        tmp_path / "scene.mvr",
        fixtures=[
            {"name": "Spot A", "uuid": "11111111-1111-1111-1111-111111111111", "address": 1},
        ],
    )

    api = _make_api(tmp_path, library_dir)
    api.load_mvr(str(mvr_path))
    api.run_export(str(tmp_path / "out.mvr"))
    assert api.get_state()["data"]["export"]["done"] is True

    result = api.reset_export()
    assert result["ok"] is True
    assert result["data"]["export"]["done"] is False


def test_unknown_type_key_returns_error(tmp_path):
    api = _make_api(tmp_path)
    result = api.set_gdtf("does-not-exist", "Spot A")
    assert result["ok"] is False
    assert "error" in result


def test_get_version(tmp_path):
    api = _make_api(tmp_path)
    result = api.get_version()
    assert result == {"ok": True, "data": "0.1.0"}
