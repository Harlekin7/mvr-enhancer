"""Tests fuer die lokale GDTF-Bibliothek (JSON-Cache + Ordner-Scan, Vorschlaege)."""

import zipfile

from mvr_enhancer.core import gdtf as gdtf_module
from mvr_enhancer.core.gdtf import find_all_gdtf_suggestions, load_gdtf_library, parse_gdtf
from tests.builders import build_gdtf


def _write_gdtf_zip(path, entries: dict[str, bytes]):
    """Schreibt ein rohes ZIP mit .gdtf-Endung (fuer Fehlerfall-Tests)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


# ──── parse_gdtf: Robustheit gegen defekte Dateien (Review I2) ────


def test_parse_gdtf_zip_without_description(tmp_path):
    """pygdtf wirft hier KeyError — parse_gdtf muss None liefern, nicht werfen."""
    path = _write_gdtf_zip(tmp_path / "no_description.gdtf", {"readme.txt": b"nope"})
    assert parse_gdtf(str(path)) is None


def test_parse_gdtf_empty_description(tmp_path):
    """Leere description.xml: pygdtf wirft IndexError — muss abgefangen werden."""
    path = _write_gdtf_zip(tmp_path / "empty_description.gdtf", {"description.xml": b""})
    assert parse_gdtf(str(path)) is None


def test_parse_gdtf_rejects_broken_xml_stub(tmp_path):
    """pygdtf liefert bei kaputtem XML einen Platzhalter statt einer Exception.

    Der Stub heisst ``Original File Had Broken XML`` (Hersteller ``PyGDTF``)
    und wuerde sonst als echte Fixture in die Bibliothek wandern und dort
    jeden Fixture-Namen mit einem Muell-Match "gewinnen" lassen.
    """
    path = _write_gdtf_zip(
        tmp_path / "broken_xml.gdtf",
        {"description.xml": b"<GDTF><FixtureType Name='x'>"},
    )
    assert parse_gdtf(str(path)) is None


def test_parse_gdtf_rejects_nameless_fixture(tmp_path):
    """Eine FixtureType ohne Name ist fuer das Matching nutzlos → None."""
    path = _write_gdtf_zip(
        tmp_path / "nameless.gdtf",
        {"description.xml": b'<GDTF DataVersion="1.2"><FixtureType Name="" '
                            b'Manufacturer="X"><DMXModes/></FixtureType></GDTF>'},
    )
    assert parse_gdtf(str(path)) is None


def test_library_scan_survives_one_malformed_gdtf(tmp_path):
    """Eine defekte Datei darf das Matching fuer alle anderen nicht kippen."""
    build_gdtf(tmp_path / "Testlight@BeamOne@rev1.gdtf",
               manufacturer="Testlight", name="Beam One")
    _write_gdtf_zip(tmp_path / "broken.gdtf", {"readme.txt": b"nope"})
    _write_gdtf_zip(tmp_path / "empty.gdtf", {"description.xml": b""})

    library = load_gdtf_library(str(tmp_path), force_reload=True)

    assert list(library) == ["Beam One"]


# ──── Billion-Laughs-Schutz fuer pygdtfs xml.etree (Review I15) ────

_BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE gdtf [
<!ENTITY a "aaaaaaaaaa">
<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
<!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">
]>
<GDTF DataVersion="1.2"><FixtureType Name="&e;" Manufacturer="&e;"/></GDTF>
"""


def test_parse_gdtf_rejects_entity_expansion(tmp_path):
    """pygdtf parst mit der ungeschuetzten stdlib — defuse_stdlib() muss greifen.

    ``mvr_enhancer/__init__.py`` ruft ``defusedxml.defuse_stdlib()`` beim Import
    des Pakets auf; dadurch wirft schon pygdtfs eigener ``ElementTree``-Aufruf
    bei Entity-Definitionen, und ``parse_gdtf`` fangt das zu ``None`` ab.
    """
    path = _write_gdtf_zip(tmp_path / "bomb.gdtf", {"description.xml": _BILLION_LAUGHS})
    assert parse_gdtf(str(path)) is None


def test_library_scan_survives_entity_expansion(tmp_path):
    path = _write_gdtf_zip(tmp_path / "bomb.gdtf", {"description.xml": _BILLION_LAUGHS})
    build_gdtf(tmp_path / "Testlight@BeamOne@rev1.gdtf",
               manufacturer="Testlight", name="Beam One")

    library = load_gdtf_library(str(tmp_path), force_reload=True)

    assert list(library) == ["Beam One"]
    assert path.is_file()


def test_scan_plain_gdtf_folder(tmp_path):
    """Zwei rohe .gdtf-Dateien ohne JSON-Cache werden beim Laden erkannt."""
    build_gdtf(
        tmp_path / "Testlight@BeamOne@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam One",
    )
    build_gdtf(
        tmp_path / "Testlight@BeamTwo@rev1.gdtf",
        manufacturer="Testlight",
        name="Beam Two",
    )

    library = load_gdtf_library(str(tmp_path), force_reload=True)

    assert len(library) == 2
    assert "Beam One" in library
    assert "Beam Two" in library

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 2


def test_broken_gdtf_skipped(tmp_path):
    """Eine Textdatei mit .gdtf-Endung darf die Bibliothek nicht zum Absturz bringen."""
    broken = tmp_path / "not_really_a_gdtf.gdtf"
    broken.write_text("this is not a zip file", encoding="utf-8")

    library = load_gdtf_library(str(tmp_path), force_reload=True)

    assert library == {}
    # Keine JSON-Cache-Datei fuer die kaputte Datei erzeugt.
    assert list(tmp_path.glob("*.json")) == []


def test_suggestions_sorted_and_thresholded(tmp_path):
    build_gdtf(
        tmp_path / "Testlight@GLPX5@rev1.gdtf",
        manufacturer="GLP",
        name="GLP X5",
    )
    build_gdtf(
        tmp_path / "Testlight@GLPImpressionX5@rev1.gdtf",
        manufacturer="GLP",
        name="GLP Impression X5",
    )
    build_gdtf(
        tmp_path / "Testlight@RobeSpiider@rev1.gdtf",
        manufacturer="Robe",
        name="Robe Spiider",
    )

    library = load_gdtf_library(str(tmp_path), force_reload=True)
    assert len(library) == 3

    suggestions = find_all_gdtf_suggestions(["GLP X5"], library, {})

    assert "GLP X5" in suggestions
    matches = suggestions["GLP X5"]

    # Robe Spiider (score 0.0) muss durch den threshold (>0.3) rausfallen.
    names = [fixture.name for fixture, _score in matches]
    assert "Robe Spiider" not in names

    # Absteigend sortiert.
    scores = [score for _fixture, score in matches]
    assert scores == sorted(scores, reverse=True)

    # Exakter Treffer zuerst mit Score 1.0.
    assert matches[0][0].name == "GLP X5"
    assert matches[0][1] == 1.0


def test_suggestions_param_topn(tmp_path):
    build_gdtf(
        tmp_path / "Testlight@GLPX5@rev1.gdtf",
        manufacturer="GLP",
        name="GLP X5",
    )
    build_gdtf(
        tmp_path / "Testlight@GLPImpressionX5@rev1.gdtf",
        manufacturer="GLP",
        name="GLP Impression X5",
    )
    build_gdtf(
        tmp_path / "Testlight@GLPX5Fos@rev1.gdtf",
        manufacturer="GLP",
        name="GLP X5 FOS",
    )

    library = load_gdtf_library(str(tmp_path), force_reload=True)
    assert len(library) == 3

    suggestions = find_all_gdtf_suggestions(["GLP X5"], library, {}, top_n=1)

    assert len(suggestions["GLP X5"]) == 1
    assert suggestions["GLP X5"][0][0].name == "GLP X5"


def test_reload_without_changes_hits_memory_cache(tmp_path, monkeypatch):
    """An unchanged directory must be a pure in-memory cache hit on reload.

    Regression test: the folder-scan used to capture the directory mtime
    *before* writing new JSON caches, so the stored mtime went stale
    immediately and every subsequent (non-forced) call re-scanned the whole
    directory. Fixed by re-stat()ing after the write loop.
    """
    build_gdtf(
        tmp_path / "Testlight@BeamOne@rev1.gdtf", manufacturer="Testlight", name="Beam One",
    )
    build_gdtf(
        tmp_path / "Testlight@BeamTwo@rev1.gdtf", manufacturer="Testlight", name="Beam Two",
    )

    library_dir = str(tmp_path)
    first = load_gdtf_library(library_dir, force_reload=True)
    assert len(first) == 2

    calls = {"count": 0}
    original_parse_gdtf = gdtf_module.parse_gdtf

    def counting_parse_gdtf(path):
        calls["count"] += 1
        return original_parse_gdtf(path)

    monkeypatch.setattr(gdtf_module, "parse_gdtf", counting_parse_gdtf)

    second = load_gdtf_library(library_dir)  # no force_reload -> should hit the mtime cache

    assert second is first
    assert calls["count"] == 0


def test_reload_skips_already_covered_raw_files(tmp_path, monkeypatch):
    """A forced reload must not re-parse .gdtf files already covered by a JSON cache.

    Regression test: the folder-scan called parse_gdtf() unconditionally for
    every raw .gdtf file before checking whether it was already represented
    in the library, so every reload re-parsed every raw file. Fixed by
    recording the covering JSON cache's ``source_file`` and skipping raw
    files already covered before parsing them.
    """
    build_gdtf(
        tmp_path / "Testlight@BeamOne@rev1.gdtf", manufacturer="Testlight", name="Beam One",
    )
    build_gdtf(
        tmp_path / "Testlight@BeamTwo@rev1.gdtf", manufacturer="Testlight", name="Beam Two",
    )

    library_dir = str(tmp_path)
    first = load_gdtf_library(library_dir, force_reload=True)
    assert len(first) == 2

    calls = {"count": 0}
    original_parse_gdtf = gdtf_module.parse_gdtf

    def counting_parse_gdtf(path):
        calls["count"] += 1
        return original_parse_gdtf(path)

    monkeypatch.setattr(gdtf_module, "parse_gdtf", counting_parse_gdtf)

    # force_reload=True bypasses the mtime shortcut, exercising the raw-scan
    # loop directly: it must still skip already-covered files.
    second = load_gdtf_library(library_dir, force_reload=True)

    assert len(second) == 2
    assert calls["count"] == 0


def test_load_survives_cache_write_failure(tmp_path, monkeypatch):
    """A cache-write failure (e.g. read-only/full library dir) must not raise.

    load_gdtf_library is a read-oriented call; a failing _save_cache() call
    during the folder-scan's cache-write step must be logged and swallowed,
    not propagate out of an otherwise successful load.
    """
    build_gdtf(
        tmp_path / "Testlight@BeamOne@rev1.gdtf", manufacturer="Testlight", name="Beam One",
    )

    def failing_save_cache(library_dir, fixture, source_file=""):
        raise OSError("read-only filesystem (simulated)")

    monkeypatch.setattr(gdtf_module, "_save_cache", failing_save_cache)

    library = load_gdtf_library(str(tmp_path), force_reload=True)

    assert len(library) == 1
    assert "Beam One" in library
    # No JSON cache was written because _save_cache was made to fail.
    assert list(tmp_path.glob("*.json")) == []
