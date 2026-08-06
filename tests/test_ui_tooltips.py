"""Guard-Tests fuer die statische UI: gestrichene Buttons bleiben draussen,
erklaerende title-Attribute bleiben drin (siehe v0.3-Spec)."""

import pathlib

_INDEX = pathlib.Path(__file__).resolve().parent.parent / "mvr_enhancer" / "ui" / "index.html"


def _html() -> str:
    return _INDEX.read_text(encoding="utf-8")


def test_cut_buttons_are_gone():
    html = _html()
    assert "btn-overrides" not in html, "Overrides teilen ist gestrichen (v0.3-Spec F1)"
    assert "btn-diff" not in html, "Diff zum letzten Export ist gestrichen (v0.3-Spec F1)"
    assert "Diff zum letzten Export" not in html


_EXPECTED_TITLES = {
    "chk-gruppieren": "Fasst Fixtures im Export nach ihrer Position",
    "seg-single": "Alles in einem Layer",
    "seg-per-layer": "3D-Objekte bleiben in ihren Original-Layern",
    "filter-problems": "Zeigt nur Typen mit offenen Punkten",
    "score-th": "Score-Legende",
    "export-uuid-row": "grandMA3 erkennt Re-Importe wieder",
    "es-matched": "Fixtures mit konkreter GDTF-Zuordnung",
    "es-embedded": "eingebettet",
    "es-meshes": "3D-Geometrien",
    "es-positions": "Positions-Gruppen im Export",
    "btn-share-login": "GDTF-Share-Datenbank",
}


def test_static_tooltips_present():
    html = _html()
    for anchor, fragment in _EXPECTED_TITLES.items():
        assert fragment in html, f"Tooltip-Fragment fuer {anchor} fehlt: {fragment!r}"
