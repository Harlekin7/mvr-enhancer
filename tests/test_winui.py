"""Tests fuer die dunkle Titelleiste (winui.py).

Die DWM-Aufrufe existieren nur auf Windows; hier werden ``sys.platform``
und ``ctypes.windll`` gemockt, damit die Logik (Attribut-Fallback fuer
alte Windows-10-Builds, Windows-11-Farbattribute, Frame-Redraw) auch auf
Linux/CI deterministisch geprueft werden kann.
"""

import ctypes

from mvr_enhancer import winui


class _FakeHandle:
    def __init__(self, value):
        self._value = value

    def ToInt64(self):  # noqa: N802 — .NET-IntPtr-API
        return self._value


class _FakeNative:
    def __init__(self, value):
        self.Handle = _FakeHandle(value)


class _FakeWindow:
    def __init__(self, value=4711):
        self.native = _FakeNative(value)


class _FakeDwm:
    """Zeichnet DwmSetWindowAttribute-Aufrufe auf; ``fail_attrs`` liefern != 0."""

    def __init__(self, fail_attrs=()):
        self.calls = []
        self.fail_attrs = set(fail_attrs)

    def DwmSetWindowAttribute(self, hwnd, attr, value_ref, size):  # noqa: N802
        value = ctypes.cast(value_ref, ctypes.POINTER(ctypes.c_int)).contents.value
        self.calls.append((hwnd, attr, value))
        return 1 if attr in self.fail_attrs else 0


class _FakeUser32:
    def __init__(self):
        self.setwindowpos_calls = []

    def SetWindowPos(self, hwnd, after, x, y, w, h, flags):  # noqa: N802
        self.setwindowpos_calls.append((hwnd, flags))
        return 1

    def FindWindowW(self, cls, title):  # noqa: N802
        return 0


class _FakeWindll:
    def __init__(self, dwm, user32):
        self.dwmapi = dwm
        self.user32 = user32


def _patch_windows(monkeypatch, *, build=19045, fail_attrs=()):
    dwm = _FakeDwm(fail_attrs=fail_attrs)
    user32 = _FakeUser32()
    monkeypatch.setattr(winui.sys, "platform", "win32")
    monkeypatch.setattr(winui, "_windows_build", lambda: build)
    monkeypatch.setattr(winui.ctypes, "windll", _FakeWindll(dwm, user32), raising=False)
    return dwm, user32


def test_noop_on_non_windows():
    # Darf auf Linux/macOS schlicht nichts tun und nie werfen.
    winui.apply_dark_titlebar(object(), "Titel")


def test_find_hwnd_via_native_handle():
    assert winui._find_hwnd(_FakeWindow(4711), "Titel") == 4711


def test_find_hwnd_without_native_returns_zero():
    # Ohne native-Objekt und ohne echtes user32 (Linux) bleibt nur 0.
    assert winui._find_hwnd(object(), "Titel") == 0


def test_sets_dark_mode_and_redraws_frame_on_windows_10(monkeypatch):
    dwm, user32 = _patch_windows(monkeypatch, build=19045)

    winui.apply_dark_titlebar(_FakeWindow(42), "Titel")

    assert (42, winui._DWMWA_USE_IMMERSIVE_DARK_MODE, 1) in dwm.calls
    # Windows 10 (< 22000): keine Caption-/Border-Farbe setzen.
    attrs = [attr for _hwnd, attr, _value in dwm.calls]
    assert winui._DWMWA_CAPTION_COLOR not in attrs
    assert winui._DWMWA_BORDER_COLOR not in attrs
    # Frame-Redraw muss angestossen werden, sonst bleibt die Leiste weiss.
    assert user32.setwindowpos_calls == [(42, winui._SWP_REDRAW_FRAME)]


def test_falls_back_to_old_attribute_on_old_windows_10(monkeypatch):
    dwm, _user32 = _patch_windows(
        monkeypatch, build=17763, fail_attrs=(winui._DWMWA_USE_IMMERSIVE_DARK_MODE,)
    )

    winui.apply_dark_titlebar(_FakeWindow(42), "Titel")

    assert (42, winui._DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1) in dwm.calls


def test_sets_caption_and_border_color_on_windows_11(monkeypatch):
    dwm, _user32 = _patch_windows(monkeypatch, build=22631)

    winui.apply_dark_titlebar(_FakeWindow(42), "Titel")

    assert (42, winui._DWMWA_CAPTION_COLOR, winui._CAPTION_COLORREF) in dwm.calls
    assert (42, winui._DWMWA_BORDER_COLOR, winui._CAPTION_COLORREF) in dwm.calls
