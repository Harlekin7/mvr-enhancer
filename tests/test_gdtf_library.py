"""Tests fuer die lokale GDTF-Bibliothek (JSON-Cache + Ordner-Scan, Vorschlaege)."""

from mvr_enhancer.core.gdtf import find_all_gdtf_suggestions, load_gdtf_library
from tests.builders import build_gdtf


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
