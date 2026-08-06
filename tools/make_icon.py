"""Erzeugt ``build/app.ico`` — das Anwendungs-Icon fuer den PyInstaller-Build.

Quelle: Motiv „3a" aus dem Design-Handoff (Ordner ``design_handoff_app_icon/``),
fertig gerenderte PNGs in mehreren Groessen (16–256 px). Das Skript packt diese
als PNG-Frames in einen ICO-Container (Windows Vista+).

**Der ICO-Container** wird hier in reinem Python zusammengesetzt: Ein ICO darf
seit Windows Vista PNG-Frames enthalten, also werden die Handoff-PNGs
eingesammelt und der 6-Byte-Header plus die 16-Byte-Verzeichniseintraege
selbst geschrieben. Das `build/app.ico` ist im Repo eingecheckt — der Build
braucht dieses Skript also nicht. Es existiert, damit das Icon reproduzierbar
bleibt:

    .venv\\Scripts\\python tools\\make_icon.py
"""

import argparse
import pathlib
import struct

_SIZES = (16, 24, 32, 48, 64, 128, 256)
_PNG_DIR = pathlib.Path(__file__).resolve().parent.parent / "design_handoff_app_icon" / "png"


def _load_frames() -> list[tuple[int, bytes]]:
    """Liest die fertigen Handoff-PNGs (16/24 = Small-Variante, Rest = Master)."""
    frames = []
    for size in _SIZES:
        png = _PNG_DIR / f"app-icon-{size}.png"
        if not png.is_file():
            raise SystemExit(f"Handoff-PNG fehlt: {png}")
        frames.append((size, png.read_bytes()))
    return frames


def _build_ico(frames: list[tuple[int, bytes]]) -> bytes:
    """Setzt PNG-Frames zu einer ICO-Datei zusammen (Vista+ PNG-in-ICO).

    Aufbau: ``ICONDIR`` (6 Byte: reserved, type=1, count) gefolgt von je einem
    16-Byte ``ICONDIRENTRY`` pro Frame und danach den Bilddaten. Eine Breite/
    Hoehe von 256 wird als ``0`` kodiert, weil das Feld nur ein Byte hat.
    """
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)
    offset = len(header) + 16 * count

    entries = bytearray()
    payload = bytearray()
    for size, data in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dim,          # width
            dim,          # height
            0,            # palette entries (0 = no palette)
            0,            # reserved
            1,            # color planes
            32,           # bits per pixel
            len(data),    # bytes in resource
            offset,       # offset of image data
        )
        payload += data
        offset += len(data)

    return bytes(header) + bytes(entries) + bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output",
        default=str(pathlib.Path(__file__).resolve().parent.parent / "build" / "app.ico"),
        help="Zielpfad der .ico-Datei (Standard: build/app.ico)",
    )
    args = parser.parse_args()

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    frames = _load_frames()
    output.write_bytes(_build_ico(frames))

    print(f"Icon geschrieben: {output} ({output.stat().st_size} bytes, "
          f"{len(frames)} Groessen: {', '.join(str(s) for s, _ in frames)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
