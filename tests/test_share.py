"""Tests fuer den GDTF Share API-Client (login, gecachte Liste, Suche, Download).

Alle Tests ersetzen ausschliesslich ``GdtfShareClient._request`` per
monkeypatch — es findet zu keinem Zeitpunkt echte Netzwerk-I/O statt.
"""

import json
import os

from mvr_enhancer.core import share as share_module
from mvr_enhancer.core.share import GdtfShareClient
from tests.builders import build_gdtf


def test_login_success_sets_state(monkeypatch):
    client = GdtfShareClient()
    seen = {}

    def fake_request(method, slug, params=None, data=None):
        seen["method"] = method
        seen["slug"] = slug
        seen["data"] = data
        return 200, json.dumps({"result": True}).encode()

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.login("alice", "secret") is True
    assert client.logged_in is True
    assert client.last_error == ""
    assert seen["method"] == "POST"
    assert seen["slug"] == "login.php"
    assert seen["data"] == {"user": "alice", "password": "secret"}


def test_login_failure_sets_error(monkeypatch):
    client = GdtfShareClient()

    def fake_request(method, slug, params=None, data=None):
        return 401, json.dumps({"error": "invalid credentials"}).encode()

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.login("alice", "wrong") is False
    assert client.logged_in is False
    assert client.last_error == "invalid credentials"


def _fixture_entries():
    return [
        {"rid": 1, "manufacturer": "GLP", "fixture": "impression X5", "modes": []},
        {"rid": 2, "manufacturer": "GLP", "fixture": "impression X4", "modes": []},
        {"rid": 3, "manufacturer": "Robe", "fixture": "Spiider", "modes": []},
    ]


def test_search_filters_and_limits(monkeypatch):
    client = GdtfShareClient()
    client.logged_in = True

    def fake_request(method, slug, params=None, data=None):
        return 200, json.dumps({"result": True, "list": _fixture_entries()}).encode()

    monkeypatch.setattr(client, "_request", fake_request)

    # "GLP" matches 2 of the 3 entries (rid 1, 2); limit=1 must truncate to 1.
    unlimited = client.search("GLP", limit=50)
    assert len(unlimited) == 2
    assert {item["rid"] for item in unlimited} == {1, 2}

    limited = client.search("GLP", limit=1)
    assert len(limited) == 1
    assert limited[0]["rid"] == 1


def test_download_writes_and_imports(tmp_path, monkeypatch):
    source = build_gdtf(
        tmp_path / "source.gdtf", manufacturer="Testlight", name="Beam One",
    )
    gdtf_bytes = source.read_bytes()

    client = GdtfShareClient()
    client.logged_in = True

    def fake_request(method, slug, params=None, data=None):
        assert slug == "downloadFile.php"
        assert params == {"rid": 42}
        return 200, gdtf_bytes

    monkeypatch.setattr(client, "_request", fake_request)

    library_dir = tmp_path / "library"
    fixture = client.download(42, str(library_dir))

    assert fixture is not None
    assert fixture.manufacturer == "Testlight"
    assert fixture.name == "Beam One"
    assert client.last_error == ""
    assert list(library_dir.glob("*.gdtf"))
    assert list(library_dir.glob("*.json"))


def test_download_size_limit(tmp_path, monkeypatch):
    client = GdtfShareClient()
    client.logged_in = True

    monkeypatch.setattr(share_module, "MAX_GDTF_DOWNLOAD_SIZE", 10)

    def fake_request(method, slug, params=None, data=None):
        return 200, b"x" * 1000

    monkeypatch.setattr(client, "_request", fake_request)

    library_dir = tmp_path / "library"
    result = client.download(1, str(library_dir))

    assert result is None
    assert client.last_error
    assert list(library_dir.glob("*")) == []


def test_filename_for_download_strips_path_traversal():
    """A malicious/odd Content-Disposition must not escape library_dir."""
    client = GdtfShareClient()
    client._last_content_disposition = 'attachment; filename="../../evil.gdtf"'

    filename = client._filename_for_download(1)

    assert filename == "evil.gdtf"
    assert os.sep not in filename
    assert "/" not in filename


def test_filename_for_download_normal_roundtrip():
    """A well-formed Content-Disposition filename is used as-is (basename)."""
    client = GdtfShareClient()
    client._last_content_disposition = (
        'attachment; filename="Vendor@Fixture@rev.gdtf"'
    )

    filename = client._filename_for_download(1)

    assert filename == "Vendor@Fixture@rev.gdtf"


def test_list_cache_roundtrip(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "share_list_cache.json")
    fixtures = _fixture_entries()

    client = GdtfShareClient(cache_path=cache_path)
    client.logged_in = True
    call_count = {"n": 0}

    def fake_request(method, slug, params=None, data=None):
        call_count["n"] += 1
        return 200, json.dumps({"result": True, "list": fixtures}).encode()

    monkeypatch.setattr(client, "_request", fake_request)

    first = client.get_fixture_list()
    assert first == fixtures
    assert call_count["n"] == 1
    assert os.path.isfile(cache_path)

    # A brand-new client sharing the same cache_path must serve the second
    # call straight from disk, with zero network calls.
    client2 = GdtfShareClient(cache_path=cache_path)
    client2.logged_in = True

    def fail_request(method, slug, params=None, data=None):
        raise AssertionError("network must not be called on a cache hit")

    monkeypatch.setattr(client2, "_request", fail_request)

    second = client2.get_fixture_list()
    assert second == fixtures

    # force_refresh=True must bypass the cache and hit the network.
    monkeypatch.setattr(client2, "_request", fake_request)
    call_count["n"] = 0
    third = client2.get_fixture_list(force_refresh=True)
    assert third == fixtures
    assert call_count["n"] == 1
