"""Windows-spezifische Fenster-Optik: dunkle Titelleiste und Rahmen.

Portiert aus vw-tool-gpa ``app/vectorwatch/ui/theme.py`` (apply_dark_titlebar):
pywebview zeichnet nur den Fensterinhalt — Titelleiste und Rahmen kommen vom
System und sind auf Windows 10 unabhaengig vom App-Theme weiss.
``DwmSetWindowAttribute`` schaltet beides pro Fenster dauerhaft dunkel,
unabhaengig vom Hell/Dunkel-Modus des Systems:

- ``DWMWA_USE_IMMERSIVE_DARK_MODE`` (20, auf aelteren Windows-10-Builds 19)
  aktiviert die dunkle System-Titelleiste — der einzige Hebel, den
  Windows 10 dafuer anbietet.
- Ab Windows 11 (Build 22000) werden Titelleiste und Rahmen zusaetzlich
  exakt auf die App-Hintergrundfarbe gesetzt (``--navy-950`` aus
  ``ui/css/tokens.css``).
"""

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # Windows 10 Builds vor 18985
_DWMWA_BORDER_COLOR = 34  # ab Windows 11
_DWMWA_CAPTION_COLOR = 35  # ab Windows 11
# COLORREF ist BGR: App-Hintergrund --navy-950 #08131f -> 0x001f1308
_CAPTION_COLORREF = 0x001F1308

# SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
_SWP_REDRAW_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
# SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE (Groesse WIRD geaendert)
_SWP_NUDGE = 0x0002 | 0x0004 | 0x0010


class _Rect(ctypes.Structure):
    """Win32-RECT (left/top/right/bottom) fuer GetWindowRect."""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _windows_build() -> int:
    """Windows-Build-Nummer, 0 wenn nicht ermittelbar (Nicht-Windows)."""
    try:
        return sys.getwindowsversion().build
    except (AttributeError, OSError):
        return 0


def _find_hwnd(window, title: str) -> int:
    """Ermittelt das Win32-Handle des pywebview-Fensters.

    Bevorzugt ueber das native WinForms-Objekt (``window.native.Handle``);
    faellt auf eine Titelsuche per ``FindWindowW`` zurueck, falls sich
    pywebviews Interna aendern. Gibt 0 zurueck, wenn kein Handle auffindbar
    ist.
    """
    native = getattr(window, "native", None)
    handle = getattr(native, "Handle", None)
    for converter_name in ("ToInt64", "ToInt32"):
        converter = getattr(handle, converter_name, None)
        if converter is None:
            continue
        try:
            return int(converter())
        except (TypeError, ValueError, OverflowError):
            break
    try:
        return int(ctypes.windll.user32.FindWindowW(None, title))
    except (AttributeError, OSError):
        return 0


def apply_dark_titlebar(window, title: str) -> None:
    """Schaltet Titelleiste (ab Windows 11 auch den Rahmen) dauerhaft dunkel.

    Best-effort: jeder Fehlschlag (Windows-Version ohne das Attribut,
    fehlendes Handle) wird nur geloggt — die App bleibt voll bedienbar,
    lediglich mit heller System-Titelleiste.

    Args:
        window: pywebview-Fensterobjekt (nach dem ``shown``-Event).
        title: Fenstertitel als Fallback fuer die Handle-Suche.
    """
    if sys.platform != "win32":
        return
    hwnd = _find_hwnd(window, title)
    if not hwnd:
        log.warning("Dunkle Titelleiste: Fenster-Handle nicht gefunden")
        return
    try:
        dwm = ctypes.windll.dwmapi
        enabled = ctypes.c_int(1)
        result = dwm.DwmSetWindowAttribute(
            hwnd,
            _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(enabled),
            ctypes.sizeof(enabled),
        )
        if result != 0:
            dwm.DwmSetWindowAttribute(
                hwnd,
                _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
        if _windows_build() >= 22000:
            color = ctypes.c_int(_CAPTION_COLORREF)
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(color), ctypes.sizeof(color)
            )
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_BORDER_COLOR, ctypes.byref(color), ctypes.sizeof(color)
            )
        # Nicht-Client-Bereich neu zeichnen lassen. SWP_FRAMECHANGED allein
        # reicht auf Windows 10 nicht — die Leiste bliebe bis zur ersten
        # Aktivierung (Klick) hell. Der 1-Pixel-Groessen-Nudge zwingt DWM,
        # die Titelleiste sofort neu zu kompositieren; danach wird die
        # Originalgroesse wiederhergestellt.
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_REDRAW_FRAME)
        rect = _Rect()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 0 and height > 1:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, width, height - 1, _SWP_NUDGE
                )
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, width, height, _SWP_NUDGE
                )
        log.info("Dunkle Titelleiste aktiviert (hwnd=%s)", hwnd)
    except (AttributeError, OSError):
        log.warning("Dunkle Titelleiste konnte nicht gesetzt werden", exc_info=True)
