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
        return 200, json.dumps({"result": True}).encode(), ""

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
        return 401, json.dumps({"error": "invalid credentials"}).encode(), ""

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
        return 200, json.dumps({"result": True, "list": _fixture_entries()}).encode(), ""

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
        return 200, gdtf_bytes, ""

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
        return 200, b"x" * 1000, ""

    monkeypatch.setattr(client, "_request", fake_request)

    library_dir = tmp_path / "library"
    result = client.download(1, str(library_dir))

    assert result is None
    assert client.last_error
    assert list(library_dir.glob("*")) == []


def test_filename_for_download_strips_path_traversal():
    """A malicious/odd Content-Disposition must not escape library_dir."""
    client = GdtfShareClient()

    filename = client._filename_for_download(1, 'attachment; filename="../../evil.gdtf"')

    assert filename == "evil.gdtf"
    assert os.sep not in filename
    assert "/" not in filename


def test_filename_for_download_normal_roundtrip():
    """A well-formed Content-Disposition filename is used as-is (basename)."""
    client = GdtfShareClient()

    filename = client._filename_for_download(
        1, 'attachment; filename="Vendor@Fixture@rev.gdtf"'
    )

    assert filename == "Vendor@Fixture@rev.gdtf"


def test_filename_for_download_falls_back_without_header():
    client = GdtfShareClient()
    assert client._filename_for_download(7, "") == "fixture_7.gdtf"


# ──── Content-Disposition kommt als Rueckgabewert, nicht als Instanz-Zustand ────


def test_download_uses_content_disposition_from_request_result(tmp_path, monkeypatch):
    """The CD filename must travel with its own response, not via self.

    Regression for the thread-safety finding: the Content-Disposition header
    used to be stashed on the client (``self._last_content_disposition``), so
    two concurrent downloads could swap filenames and embed the wrong GDTF.
    It is now the third element of ``_request``'s return value and threaded
    through as a local — which also gives the previously untested CD path
    actual coverage.
    """
    source = build_gdtf(
        tmp_path / "source.gdtf", manufacturer="Vendor", name="Beam One",
    )
    gdtf_bytes = source.read_bytes()

    client = GdtfShareClient()
    client.logged_in = True

    def fake_request(method, slug, params=None, data=None):
        return 200, gdtf_bytes, 'attachment; filename="Vendor@Beam One@rev3.gdtf"'

    monkeypatch.setattr(client, "_request", fake_request)

    library_dir = tmp_path / "library"
    fixture = client.download(42, str(library_dir))

    assert fixture is not None
    assert (library_dir / "Vendor@Beam One@rev3.gdtf").is_file()
    # Revision is derived from the filename convention -> proves the CD name won.
    assert fixture.revision == "rev3"
    assert not any(p.name.endswith(".part") for p in library_dir.iterdir())


def test_download_never_retries_more_than_once_on_401(tmp_path, monkeypatch):
    """The 401-relogin guard must be per-call state, not a client attribute."""
    client = GdtfShareClient()
    client.logged_in = True
    client._username = "alice"
    client._password = "secret"

    calls = {"download": 0, "login": 0}

    def fake_request(method, slug, params=None, data=None):
        if slug == "login.php":
            calls["login"] += 1
            return 200, json.dumps({"result": True}).encode(), ""
        calls["download"] += 1
        return 401, b"{}", ""

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.download(1, str(tmp_path / "library")) is None
    # One initial attempt + exactly one retry after a successful relogin.
    assert calls["download"] == 2
    assert calls["login"] == 1
    assert client.last_error


# ──── Fehlgeschlagener Download hinterlaesst keine Ruine (Review I16) ────


def test_failed_download_leaves_no_residue(tmp_path, monkeypatch):
    """Unparseable download bytes must not land in the library at all.

    Previously the bytes were written to their final name and only *then*
    handed to import_gdtf() — a corrupt download therefore stayed in the
    library folder forever, where every later scan retried and failed on it.
    """
    client = GdtfShareClient()
    client.logged_in = True

    def fake_request(method, slug, params=None, data=None):
        return 200, b"this is not a gdtf archive", 'attachment; filename="Bad@File@r1.gdtf"'

    monkeypatch.setattr(client, "_request", fake_request)

    library_dir = tmp_path / "library"
    result = client.download(1, str(library_dir))

    assert result is None
    assert client.last_error
    assert list(library_dir.iterdir()) == []


def test_list_cache_roundtrip(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "share_list_cache.json")
    fixtures = _fixture_entries()

    client = GdtfShareClient(cache_path=cache_path)
    client.logged_in = True
    call_count = {"n": 0}

    def fake_request(method, slug, params=None, data=None):
        call_count["n"] += 1
        return 200, json.dumps({"result": True, "list": fixtures}).encode(), ""

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
