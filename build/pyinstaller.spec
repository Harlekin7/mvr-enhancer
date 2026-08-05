# -*- mode: python -*-
"""PyInstaller spec for the MVR Enhancer onefile/windowed build.

Invoke from the repository root:

    .venv\\Scripts\\pyinstaller build\\pyinstaller.spec --noconfirm --distpath dist

``SPECPATH`` (injected by PyInstaller) is this file's directory, i.e.
``<repo>/build``. All paths below are derived from it so the spec works
regardless of the caller's current working directory.
"""

import os

REPO_ROOT = os.path.dirname(SPECPATH)  # noqa: F821 - SPECPATH is injected by PyInstaller
ENTRY_POINT = os.path.join(REPO_ROOT, "mvr_enhancer", "__main__.py")
UI_SRC = os.path.join(REPO_ROOT, "mvr_enhancer", "ui")

# Destination is relative ("mvr_enhancer/ui") so the frozen layout under
# sys._MEIPASS matches the source-tree layout that mvr_enhancer/main.py
# resolves via `_MEIPASS / "mvr_enhancer" / "ui" / "index.html"`. Written as a
# literal forward-slash string (PyInstaller normalizes it) so the agreement
# test in tests/test_main.py can assert on it by reading this file as text.
UI_DEST = "mvr_enhancer/ui"

datas = [(UI_SRC, UI_DEST)]

# App-Icon: erzeugt von tools/make_icon.py (siehe dort), im Repo eingecheckt.
ICON = os.path.join(REPO_ROOT, "build", "app.ico")

hiddenimports = [
    "pygdtf",
    "certifi",
    "defusedxml",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
]

a = Analysis(  # noqa: F821 - Analysis/PYZ/EXE are injected by PyInstaller
    [ENTRY_POINT],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MVR Enhancer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=ICON,
)
