"""Erzeugt ``build/app.ico`` — das Anwendungs-Icon fuer den PyInstaller-Build.

Motiv laut Design-Spec §9: ein grosses „G" (Barlow Condensed Bold, weiss) auf
einem Verlauf von ``#1e7cc4`` (oben links) nach ``#5caedd`` (unten rechts) mit
abgerundeten Ecken.

Warum diese ungewoehnliche Zweiteilung:

* **Rendering** laeuft ueber PowerShell + .NET ``System.Drawing`` — Text mit
  einer echten Schrift zu rastern braucht eine Font-Engine, und Pillow ist
  (bewusst) keine Dependency dieses Projekts. .NET liegt auf jedem Windows,
  das die App ohnehin voraussetzt, bereits vor.
* **Der ICO-Container** wird hier in reinem Python zusammengesetzt: die von
  ``System.Drawing`` erreichbaren Wege (``Icon.FromHandle(bmp.GetHicon())``)
  liefern nur 32×32 und verlieren den Alphakanal. Ein ICO darf seit Windows
  Vista PNG-Frames enthalten, also werden hier mehrere PNGs eingesammelt und
  der 6-Byte-Header plus die 16-Byte-Verzeichniseintraege selbst geschrieben.

Das Ergebnis ist im Repo eingecheckt (``build/app.ico``) — der Build braucht
dieses Skript also nicht. Es existiert, damit das Icon reproduzierbar bleibt:

    .venv\\Scripts\\python tools\\make_icon.py
"""

import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile

# Groessen im ICO. 256 ist Pflicht fuer die grosse Explorer-Ansicht, 16/32/48
# fuer Taskleiste, Titelleiste und Detailansicht.
_SIZES = (16, 32, 48, 64, 128, 256)

_GRADIENT_FROM = "#1e7cc4"
_GRADIENT_TO = "#5caedd"

# PowerShell-Renderer. Zeichnet pro Groesse ein PNG mit Alphakanal.
_RENDER_PS1 = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$outDir = $args[0]
$sizes  = $args[1] -split ','
$from   = [System.Drawing.ColorTranslator]::FromHtml($args[2])
$to     = [System.Drawing.ColorTranslator]::FromHtml($args[3])

foreach ($sizeText in $sizes) {
    $size = [int]$sizeText
    $bmp = New-Object System.Drawing.Bitmap($size, $size,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::Transparent)

    # Verlauf oben links -> unten rechts.
    $rect  = New-Object System.Drawing.Rectangle(0, 0, $size, $size)
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        $rect, $from, $to, 45.0)

    # Abgerundetes Quadrat (Radius ~22% der Kantenlaenge, wie Windows-Icons).
    $r = [Math]::Max(2, [int]($size * 0.22))
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $r * 2
    $path.AddArc(0, 0, $d, $d, 180, 90)
    $path.AddArc($size - $d - 1, 0, $d, $d, 270, 90)
    $path.AddArc($size - $d - 1, $size - $d - 1, $d, $d, 0, 90)
    $path.AddArc(0, $size - $d - 1, $d, $d, 90, 90)
    $path.CloseFigure()
    $g.FillPath($brush, $path)

    # "G" zentriert. Barlow Condensed ist die Marken-Schrift; wenn sie auf dem
    # Rechner fehlt, faellt .NET selbst auf eine aehnliche Schrift zurueck.
    $fontSize = [float]($size * 0.62)
    $font = New-Object System.Drawing.Font("Barlow Condensed", $fontSize,
        [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment     = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $white = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    # DrawString braucht ein RectangleF (nicht das Rectangle des Brushes).
    $textRect = New-Object System.Drawing.RectangleF(0, 0, [float]$size, [float]$size)
    $g.DrawString("G", $font, $white, $textRect, $fmt)

    $g.Dispose()
    $bmp.Save((Join-Path $outDir "icon-$size.png"),
        [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}
Write-Output "rendered"
"""


def _render_pngs(out_dir: pathlib.Path) -> list[tuple[int, bytes]]:
    """Rendert je ein PNG pro Groesse via PowerShell/.NET und liest sie ein."""
    script = out_dir / "render_icon.ps1"
    script.write_text(_RENDER_PS1, encoding="utf-8")
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script),
            str(out_dir), ",".join(str(s) for s in _SIZES),
            _GRADIENT_FROM, _GRADIENT_TO,
        ],
        capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Icon-Rendering fehlgeschlagen (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    frames = []
    for size in _SIZES:
        png = out_dir / f"icon-{size}.png"
        if not png.is_file():
            raise SystemExit(f"Erwartetes PNG fehlt: {png}")
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

    if sys.platform != "win32":
        raise SystemExit("make_icon.py braucht Windows (.NET System.Drawing).")

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        frames = _render_pngs(pathlib.Path(tmp))
        output.write_bytes(_build_ico(frames))

    print(f"Icon geschrieben: {output} ({output.stat().st_size} bytes, "
          f"{len(frames)} Groessen: {', '.join(str(s) for s, _ in frames)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
