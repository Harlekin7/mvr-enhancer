"""Fetch/generate the offline UI assets bundled with the app.

Produces (all under ``mvr_enhancer/ui/``):

- ``css/tokens.css``        -- design tokens, concatenated from the design
  handoff (colors, typography, spacing, effects -- NOT fonts.css, which only
  contains a Google Fonts ``@import``).
- ``assets/fonts/*.woff2`` + ``assets/fonts/fonts.css`` -- the webfonts used
  by the design system, downloaded once from Google Fonts and vendored so the
  app works fully offline.
- ``assets/icons.js`` -- the Lucide icon set used by the UI, inlined as a
  ``const ICONS = {...}`` map of raw SVG markup.
- ``assets/hintergrund.jpg`` -- the brand background image, copied from the
  design handoff.

This script is meant to be run once (and re-run whenever the icon/font list
changes) and its output committed, so the app never needs network access at
runtime. It is idempotent: existing output files are left alone unless
``--force`` is passed. Only the Python standard library is used.

Usage::

    .venv/Scripts/python tools/fetch_assets.py [--force]
"""

from __future__ import annotations

import argparse
import re
import shutil
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = REPO_ROOT / "mvr_enhancer" / "ui"
ASSETS_DIR = UI_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
CSS_DIR = UI_DIR / "css"
HANDOFF_DIR = REPO_ROOT / "design_handoff_mvr_export_tool"
TOKENS_SRC_DIR = HANDOFF_DIR / "design_system" / "tokens"
BACKGROUND_SRC = HANDOFF_DIR / "assets" / "backgrounds" / "hintergrund.jpg"

# Google Fonts serves woff2 (rather than woff/ttf) only to user agents it
# recognizes as supporting it -- a plain urllib UA gets ttf. Spoof Chrome.
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Families/weights required by design_handoff_mvr_export_tool/design_system/
# tokens/fonts.css:5 -- Barlow 400,500,600,700 + 400 italic; Barlow Condensed
# 500,600,700; Barlow Semi Condensed 500,600; JetBrains Mono 400,500.
GOOGLE_FONTS_CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Barlow:ital,wght@0,400;0,500;0,600;0,700;1,400"
    "&family=Barlow+Condensed:wght@500;600;700"
    "&family=Barlow+Semi+Condensed:wght@500;600"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)
# Only latin + latin-ext subsets are wanted (no cyrillic/greek/vietnamese).
WANTED_SUBSETS = {"latin", "latin-ext"}

FONT_FACE_RE = re.compile(
    r"/\*\s*(?P<subset>[\w-]+)\s*\*/\s*@font-face\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)

LUCIDE_VERSION = "0.469.0"
LUCIDE_BASE = f"https://unpkg.com/lucide-static@{LUCIDE_VERSION}/icons"
# Exactly the 19 icons used by the UI (incl. x/search/log-in for modals).
ICON_NAMES = [
    "settings-2",
    "upload",
    "file-box",
    "shield-check",
    "box",
    "link-2",
    "eraser",
    "folder-open",
    "globe",
    "info",
    "check",
    "arrow-down-to-line",
    "triangle-alert",
    "zap",
    "list-checks",
    "circle-check",
    "x",
    "search",
    "log-in",
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read()


def slugify(family: str) -> str:
    return family.lower().replace(" ", "-")


# ---------------------------------------------------------------------------
# tokens.css
# ---------------------------------------------------------------------------


def build_tokens_css(force: bool) -> None:
    out_path = CSS_DIR / "tokens.css"
    if out_path.exists() and not force:
        print(f"skip  {out_path} (exists)")
        return
    CSS_DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    for name in ("colors.css", "typography.css", "spacing.css", "effects.css"):
        text = (TOKENS_SRC_DIR / name).read_text(encoding="utf-8")
        if name == "effects.css":
            # The handoff nests the image under assets/backgrounds/, but we
            # vendor it flat at ui/assets/hintergrund.jpg -- fix the relative
            # path so it still resolves from ui/css/tokens.css.
            text = text.replace(
                'url("../assets/backgrounds/hintergrund.jpg")',
                'url("../assets/hintergrund.jpg")',
            )
        parts.append(text.rstrip() + "\n")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# background image
# ---------------------------------------------------------------------------


def copy_background(force: bool) -> None:
    dst = ASSETS_DIR / "hintergrund.jpg"
    if dst.exists() and not force:
        print(f"skip  {dst} (exists)")
        return
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BACKGROUND_SRC, dst)
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# icons.js
# ---------------------------------------------------------------------------


def normalize_svg(raw: str) -> str:
    """Strip the license/XML preamble and collapse to a single line."""
    svg = raw[raw.index("<svg") :]
    svg = re.sub(r"\s+", " ", svg)
    svg = re.sub(r"\s*>", ">", svg)
    return svg.strip()


def build_icons(force: bool) -> None:
    out_path = ASSETS_DIR / "icons.js"
    if out_path.exists() and not force:
        print(f"skip  {out_path} (exists)")
        return
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in ICON_NAMES:
        raw = fetch(f"{LUCIDE_BASE}/{name}.svg").decode("utf-8")
        entries.append((name, normalize_svg(raw)))

    lines = ["const ICONS = {"]
    for name, svg in entries:
        escaped = svg.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  "{name}": "{escaped}",')
    lines.append("};")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(entries)} icons)")


# ---------------------------------------------------------------------------
# fonts.css + woff2 files
# ---------------------------------------------------------------------------


def parse_font_face_blocks(css_text: str) -> list[dict[str, str | None]]:
    blocks = []
    for m in FONT_FACE_RE.finditer(css_text):
        body = m.group("body")
        family = re.search(r"font-family:\s*'([^']+)'", body)
        style = re.search(r"font-style:\s*(\w+)", body)
        weight = re.search(r"font-weight:\s*(\d+)", body)
        url = re.search(r"url\(([^)]+)\)", body)
        unicode_range = re.search(r"unicode-range:\s*([^;]+);", body)
        if not (family and style and weight and url):
            continue
        blocks.append(
            {
                "subset": m.group("subset"),
                "family": family.group(1),
                "style": style.group(1),
                "weight": weight.group(1),
                "url": url.group(1),
                "unicode_range": unicode_range.group(1).strip() if unicode_range else None,
            }
        )
    return blocks


def render_font_face(block: dict[str, str | None], filename: str) -> str:
    lines = [
        "@font-face {",
        f"  font-family: '{block['family']}';",
        f"  font-style: {block['style']};",
        f"  font-weight: {block['weight']};",
        "  font-display: swap;",
        f'  src: url("{filename}") format("woff2");',
    ]
    if block["unicode_range"]:
        lines.append(f"  unicode-range: {block['unicode_range']};")
    lines.append("}")
    return "\n".join(lines)


def build_fonts(force: bool) -> None:
    out_css = FONTS_DIR / "fonts.css"
    if out_css.exists() and not force:
        print(f"skip  {out_css} (exists)")
        return
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    css_text = fetch(GOOGLE_FONTS_CSS_URL).decode("utf-8")
    blocks = [b for b in parse_font_face_blocks(css_text) if b["subset"] in WANTED_SUBSETS]

    out_blocks = []
    for block in blocks:
        family_slug = slugify(str(block["family"]))
        style_suffix = "-italic" if block["style"] == "italic" else ""
        filename = f"{family_slug}-{block['weight']}{style_suffix}-{block['subset']}.woff2"
        dest = FONTS_DIR / filename

        if not dest.exists() or force:
            data = fetch(str(block["url"]))
            dest.write_bytes(data)
            print(f"wrote {dest} ({dest.stat().st_size} bytes)")
        else:
            print(f"skip  {dest} (exists)")

        out_blocks.append(render_font_face(block, filename))

    out_css.write_text("\n\n".join(out_blocks) + "\n", encoding="utf-8")
    print(f"wrote {out_css} ({out_css.stat().st_size} bytes, {len(out_blocks)} @font-face rules)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download/regenerate files even if they already exist",
    )
    args = parser.parse_args()

    build_tokens_css(args.force)
    copy_background(args.force)
    build_icons(args.force)
    build_fonts(args.force)


if __name__ == "__main__":
    main()
