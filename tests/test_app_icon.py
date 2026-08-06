"""build/app.ico muss die 7 Handoff-PNGs (16..256) als PNG-Frames enthalten."""

import pathlib
import struct

_ICO = pathlib.Path(__file__).resolve().parent.parent / "build" / "app.ico"
_HANDOFF = pathlib.Path(__file__).resolve().parent.parent / "design_handoff_app_icon" / "png"
_EXPECTED_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _read_entries(data: bytes):
    reserved, ico_type, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, ico_type) == (0, 1)
    entries = []
    for i in range(count):
        width, height, _, _, _, bpp, size, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * i
        )
        entries.append({"dim": width or 256, "size": size, "offset": offset})
    return entries


def test_ico_contains_all_handoff_sizes():
    entries = _read_entries(_ICO.read_bytes())
    assert sorted(e["dim"] for e in entries) == _EXPECTED_SIZES


def test_ico_frames_are_verbatim_handoff_pngs():
    data = _ICO.read_bytes()
    frames = {
        e["dim"]: data[e["offset"]:e["offset"] + e["size"]]
        for e in _read_entries(data)
    }
    for size in _EXPECTED_SIZES:
        expected = (_HANDOFF / f"app-icon-{size}.png").read_bytes()
        assert frames[size] == expected, f"Frame {size}px weicht vom Handoff-PNG ab"
