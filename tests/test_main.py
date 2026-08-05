"""Tests fuer den Fenster-Einstiegspunkt (``mvr_enhancer.main``).

Der Fokus liegt auf dem, was am Build haengt und sich nur hier pruefen laesst:
die Auflloesung der ``index.html`` in beiden Zustaenden (Quellbaum vs. gefroren)
und die Uebereinstimmung mit dem PyInstaller-Spec. ``run()`` selbst startet ein
echtes Fenster und wird bewusst nicht komplett ausgefuehrt — nur der Abbruch
VOR der Fenstererzeugung ist getestet.
"""

import logging
import sys
from pathlib import Path

import pytest

from mvr_enhancer import main as main_module

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_ui_path_source_tree(monkeypatch):
    """Im Quellbaum zeigt _ui_path() auf die echte, existierende index.html."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    ui_path = main_module._ui_path()

    assert ui_path == _REPO_ROOT / "mvr_enhancer" / "ui" / "index.html"
    assert ui_path.is_file()


def test_ui_path_frozen_uses_meipass(monkeypatch, tmp_path):
    """Gefroren zeigt _ui_path() unter sys._MEIPASS auf dieselbe Struktur.

    PyInstaller entpackt das Onefile-Archiv nach ``sys._MEIPASS``; das Layout
    dort muss dem Quellbaum entsprechen, sonst findet die App ihre UI nicht.
    """
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    ui_path = main_module._ui_path()

    assert ui_path == tmp_path / "mvr_enhancer" / "ui" / "index.html"


def test_pyinstaller_spec_ships_ui_to_the_path_main_resolves():
    """Agreement-Test: Spec-Ziel und _ui_path()-Erwartung muessen uebereinstimmen.

    Ein Auseinanderlaufen dieser beiden Stellen faellt sonst erst am fertigen
    Exe auf (leeres Fenster bzw. jetzt: harter Startabbruch).
    """
    spec_text = (_REPO_ROOT / "build" / "pyinstaller.spec").read_text(encoding="utf-8")

    assert '"mvr_enhancer/ui"' in spec_text

    # ... und genau dieses Ziel ist der Pfad, den _ui_path() gefroren aufloest.
    relative = main_module._ui_path().parent
    assert relative.parts[-2:] == ("mvr_enhancer", "ui")


def test_missing_ui_file_is_a_hard_failure(monkeypatch, tmp_path):
    """Fehlt die index.html, bricht der Start mit sichtbarer Meldung ab."""
    monkeypatch.setattr(
        main_module, "_ui_path", lambda: tmp_path / "nowhere" / "index.html",
    )
    monkeypatch.setattr(main_module, "_setup_logging", lambda: None)
    shown: list[str] = []
    monkeypatch.setattr(main_module, "_show_error_dialog", shown.append)

    def _boom(*args, **kwargs):
        raise AssertionError("create_window must not be reached")

    monkeypatch.setattr(main_module.webview, "create_window", _boom)

    with pytest.raises(SystemExit) as excinfo:
        main_module.run()

    assert "index.html" in str(excinfo.value)
    assert len(shown) == 1
    assert "index.html" in shown[0]


def test_setup_logging_adds_rotating_file_handler(monkeypatch, tmp_path):
    """Im windowed Build ist die Log-Datei die einzige Absturz-Spur."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        main_module._setup_logging()
        added = [h for h in root.handlers if h not in before]
        rotating = [
            h for h in added if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating) == 1
        handler = rotating[0]
        assert handler.maxBytes == 1_000_000
        assert handler.backupCount == 3
        log_file = tmp_path / "MVR Enhancer" / "mvr-enhancer.log"
        assert Path(handler.baseFilename) == log_file
        assert log_file.is_file()
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                handler.close()
                root.removeHandler(handler)


def test_setup_logging_survives_unwritable_log_dir(monkeypatch, tmp_path):
    """Ein nicht anlegbares Log-Verzeichnis darf den Start nicht verhindern."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(blocker))
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        main_module._setup_logging()  # must not raise
        assert not [
            h for h in root.handlers
            if h not in before
            and isinstance(h, logging.handlers.RotatingFileHandler)
        ]
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                handler.close()
                root.removeHandler(handler)
