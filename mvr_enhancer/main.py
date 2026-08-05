"""Fenster-Einstiegspunkt: erstellt das pywebview-Fenster und startet die App."""

import logging
import os
import sys
from pathlib import Path

import webview

from mvr_enhancer.api import Api

log = logging.getLogger(__name__)

_WINDOW_TITLE = "Groh·PA MVR Export"


def _ui_path() -> Path:
    """Loest den Pfad zur ``index.html`` auf — funktioniert auch gefroren (PyInstaller).

    Im gefrorenen Zustand liegt ``sys._MEIPASS`` auf dem temporaeren
    Entpack-Verzeichnis; im Quellbaum ist die Basis das Repo-Root
    (zwei Ebenen oberhalb dieser Datei: ``mvr_enhancer/main.py`` -> Root).
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "mvr_enhancer" / "ui" / "index.html"


def run() -> None:
    """Erstellt das Hauptfenster und startet die pywebview-Event-Loop (blockiert)."""
    logging.basicConfig(level=logging.INFO)

    ui_path = _ui_path()
    if not ui_path.is_file():
        log.error("UI-Datei nicht gefunden: %s", ui_path)

    api = Api()

    window = webview.create_window(
        _WINDOW_TITLE,
        url=str(ui_path),
        js_api=api,
        # 75% of the design's 1280×1036 reference window (user request). The UI
        # matches it with `html { zoom: 0.75 }` in css/app.css, so the layout
        # still computes against ~1280 logical px inside this smaller window.
        width=960,
        height=777,
        min_size=(830, 620),
    )
    api.set_window(window)

    debug = os.environ.get("MVR_ENHANCER_DEBUG") == "1"
    webview.start(debug=debug)
