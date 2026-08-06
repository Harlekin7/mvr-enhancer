"""Guard-Tests fuer den Bibliotheks-Picker (v0.5): Modal-Markup existiert,
das Buch-Icon ist registriert, und die Bibliothek haengt nicht mehr als
optgroup im GDTF-Dropdown (Nutzer-Vorgabe v0.5)."""

import pathlib

_UI = pathlib.Path(__file__).resolve().parent.parent / "mvr_enhancer" / "ui"


def test_lib_browse_modal_markup_present():
    html = (_UI / "index.html").read_text(encoding="utf-8")
    for anchor in ("modal-lib-browse", "lib-browse-type", "lib-browse-input", "lib-browse-results"):
        assert anchor in html, f"Picker-Anker fehlt: {anchor}"
    assert "Aus der Bibliothek" in html.replace("&auml;", "ä") or "Aus der Bibliothek" in html


def test_book_icon_registered():
    icons = (_UI / "assets" / "icons.js").read_text(encoding="utf-8")
    assert "book-open" in icons


def test_full_library_optgroup_removed_from_dropdown():
    app_js = (_UI / "js" / "app.js").read_text(encoding="utf-8")
    assert "Gesamte Bibliothek" not in app_js
    assert "btn-lib-browse" in app_js
