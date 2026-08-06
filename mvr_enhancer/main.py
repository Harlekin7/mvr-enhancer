"""Fenster-Einstiegspunkt: erstellt das pywebview-Fenster und startet die App."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import webview

from mvr_enhancer.api import Api

log = logging.getLogger(__name__)

_WINDOW_TITLE = "Groh·PA MVR Export"

# Rotierende Log-Datei: im gefrorenen, fensterlosen Build (``console=False``)
# geht ``basicConfig``s Stream-Ausgabe ins Nichts — ohne Datei-Log gibt es
# nach einem Absturz beim Nutzer keinerlei Spur.
_LOG_FILENAME = "mvr-enhancer.log"
_LOG_MAX_BYTES = 1_000_000
_LOG_BACKUP_COUNT = 3


def _log_dir() -> Path:
    """Verzeichnis fuer die Log-Datei: ``%APPDATA%/MVR Enhancer``."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MVR Enhancer"


def _setup_logging() -> None:
    """Konfiguriert Konsolen- und Datei-Logging.

    Ein Fehler beim Anlegen der Log-Datei (schreibgeschuetztes Profil,
    Roaming-Profil nicht verfuegbar) darf den Start nicht verhindern — er
    wird nur auf dem Konsolen-Handler vermerkt.
    """
    logging.basicConfig(level=logging.INFO)
    try:
        log_dir = _log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / _LOG_FILENAME,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(handler)
        log.info("Log-Datei: %s", log_dir / _LOG_FILENAME)
    except OSError as e:
        log.warning("Log-Datei konnte nicht angelegt werden: %s", e)


def _show_error_dialog(message: str) -> None:
    """Zeigt eine native Fehlermeldung — der einzige Kanal im windowed Build.

    Ohne Konsole und ohne funktionierende UI ist ``MessageBoxW`` die letzte
    Moeglichkeit, dem Nutzer ueberhaupt etwas mitzuteilen.
    """
    try:
        import ctypes

        # 0x10 = MB_ICONERROR
        ctypes.windll.user32.MessageBoxW(None, message, _WINDOW_TITLE, 0x10)
    except Exception:  # noqa: BLE001 — letzte Instanz, darf nie selbst werfen
        log.exception("Fehlerdialog konnte nicht angezeigt werden")


def _fail(message: str) -> None:
    """Loggt, meldet dem Nutzer und beendet den Prozess."""
    log.error("%s", message)
    _show_error_dialog(message)
    raise SystemExit(message)


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
    _setup_logging()

    ui_path = _ui_path()
    if not ui_path.is_file():
        # Harter Abbruch statt eines leeren Fensters: ohne index.html ist die
        # Anwendung nicht bedienbar, und ein weisses Fenster ohne Meldung waere
        # fuer den Nutzer nicht von einem Absturz zu unterscheiden. Typische
        # Ursache: ein Build, bei dem die UI-Dateien nicht mitgepackt wurden.
        _fail(
            "Die Programmdateien der Benutzeroberflaeche fehlen "
            f"({ui_path}).\n\nBitte installiere die Anwendung neu."
        )

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

    def _register_dropzone_dnd() -> None:
        # Erst nach dem Laden der Seite existiert #dropzone. Ohne diesen
        # Python-seitigen Listener reicht pywebview keine nativen Dateipfade
        # durch (siehe on_dropzone_drop) — schlaegt die Registrierung fehl,
        # bleibt die App ueber den Datei-Dialog voll bedienbar.
        try:
            element = window.dom.get_element("#dropzone")
            if element is None:
                log.warning("#dropzone nicht gefunden — Drag&Drop deaktiviert")
                return
            element.on("drop", api.on_dropzone_drop)
            log.info("Drag&Drop-Listener registriert")
        except Exception:
            log.exception("Drag&Drop-Registrierung fehlgeschlagen")

    window.events.loaded += _register_dropzone_dnd

    debug = os.environ.get("MVR_ENHANCER_DEBUG") == "1"
    webview.start(debug=debug)
