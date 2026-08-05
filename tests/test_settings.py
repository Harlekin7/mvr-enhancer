"""Tests fuer Settings-Persistenz (``mvr_enhancer/settings.py``).

Alle Tests verwenden ein temporaeres Verzeichnis als ``base_dir``, damit
kein echtes ``%APPDATA%`` beruehrt wird.
"""

import json
import os

from mvr_enhancer.settings import Settings


def test_save_load_roundtrip(tmp_path):
    base_dir = str(tmp_path)
    settings = Settings.load(base_dir)
    settings.gdtf_library_dir = "C:/GDTF"
    settings.last_export_dir = "C:/Export"
    settings.group_by_position = False
    settings.share_user = "alice"
    settings.share_password_enc = "dpapi:abc123"
    settings.add_recent("C:/one.mvr")
    settings.save()

    loaded = Settings.load(base_dir)

    assert loaded.gdtf_library_dir == "C:/GDTF"
    assert loaded.last_export_dir == "C:/Export"
    assert loaded.group_by_position is False
    assert loaded.share_user == "alice"
    assert loaded.share_password_enc == "dpapi:abc123"
    assert len(loaded.recent_files) == 1
    assert loaded.recent_files[0]["path"] == "C:/one.mvr"
    assert "ts" in loaded.recent_files[0]


def test_save_writes_config_json_atomically(tmp_path):
    base_dir = str(tmp_path)
    settings = Settings.load(base_dir)
    settings.gdtf_library_dir = "C:/GDTF"
    settings.save()

    config_path = os.path.join(base_dir, "config.json")
    assert os.path.isfile(config_path)
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["gdtf_library_dir"] == "C:/GDTF"
    # Kein Temp-Leichenschmaus im Zielverzeichnis.
    leftovers = [n for n in os.listdir(base_dir) if n != "config.json"]
    assert leftovers == []


def test_defaults_when_no_config_present(tmp_path):
    settings = Settings.load(str(tmp_path))

    assert settings.recent_files == []
    assert settings.gdtf_library_dir == ""
    assert settings.last_export_dir == ""
    assert settings.group_by_position is True
    assert settings.share_user == ""
    assert settings.share_password_enc == ""


def test_corrupt_json_falls_back_to_defaults(tmp_path):
    base_dir = str(tmp_path)
    config_path = os.path.join(base_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("{not valid json::")

    settings = Settings.load(base_dir)

    assert settings.recent_files == []
    assert settings.gdtf_library_dir == ""
    assert settings.group_by_position is True


def test_missing_keys_are_defaulted(tmp_path):
    base_dir = str(tmp_path)
    config_path = os.path.join(base_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"gdtf_library_dir": "C:/only-this"}, f)

    settings = Settings.load(base_dir)

    assert settings.gdtf_library_dir == "C:/only-this"
    assert settings.recent_files == []
    assert settings.group_by_position is True
    assert settings.share_user == ""


def test_unknown_keys_are_ignored(tmp_path):
    base_dir = str(tmp_path)
    config_path = os.path.join(base_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"gdtf_library_dir": "C:/x", "totally_unknown_key": 123}, f)

    settings = Settings.load(base_dir)

    assert settings.gdtf_library_dir == "C:/x"
    assert not hasattr(settings, "totally_unknown_key")


def test_add_recent_dedupes_case_insensitive_and_moves_to_front(tmp_path):
    settings = Settings.load(str(tmp_path))
    settings.add_recent("C:/a.mvr")
    settings.add_recent("C:/b.mvr")
    settings.add_recent("C:/A.MVR")

    assert len(settings.recent_files) == 2
    assert settings.recent_files[0]["path"] == "C:/A.MVR"
    assert settings.recent_files[1]["path"] == "C:/b.mvr"


def test_add_recent_trims_to_five(tmp_path):
    settings = Settings.load(str(tmp_path))
    for i in range(7):
        settings.add_recent(f"C:/file{i}.mvr")

    assert len(settings.recent_files) == 5
    paths = [entry["path"] for entry in settings.recent_files]
    assert paths == ["C:/file6.mvr", "C:/file5.mvr", "C:/file4.mvr", "C:/file3.mvr", "C:/file2.mvr"]


def test_add_recent_stamps_iso_timestamp(tmp_path):
    settings = Settings.load(str(tmp_path))
    settings.add_recent("C:/a.mvr")

    ts = settings.recent_files[0]["ts"]
    # Muss als ISO-Timestamp parsbar sein.
    from datetime import datetime

    datetime.fromisoformat(ts)


def test_load_default_base_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setitem(os.environ, "APPDATA", str(tmp_path))
    settings = Settings.load()
    settings.gdtf_library_dir = "C:/from-appdata"
    settings.save()

    expected_path = os.path.join(str(tmp_path), "MVR Enhancer", "config.json")
    assert os.path.isfile(expected_path)
