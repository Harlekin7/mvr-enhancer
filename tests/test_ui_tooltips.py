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
