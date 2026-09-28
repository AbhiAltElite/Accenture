"""Draw the app icon into a macOS .iconset folder. Called by build_mac_app.sh."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    """The WhyChain mark: two linked chain links on a purple tile (ui/mark.svg)."""
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pad = big * 0.06
    # A vertical blend from deep to bright purple, drawn as bands.
    top, bottom = (70, 0, 115), (161, 0, 255)
    tile = Image.new("RGBA", (big, big))
    td = ImageDraw.Draw(tile)
    for y in range(big):
        t = y / big
        td.line([(0, y), (big, y)], fill=(*(int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)), 255))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, big - pad, big - pad), radius=big * 0.22, fill=255)
    img.paste(tile, (0, 0), mask)
    links = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ld = ImageDraw.Draw(links)
    w = max(2, round(big * 0.075))
    h = big * 0.28
    cy = big / 2
    ld.rounded_rectangle((big * 0.13, cy - h / 2, big * 0.56, cy + h / 2), radius=h / 2, outline=(255, 255, 255, 255), width=w)
    ld.rounded_rectangle((big * 0.44, cy - h / 2, big * 0.87, cy + h / 2), radius=h / 2, outline=(255, 255, 255, 170), width=w)
    links = links.rotate(38, resample=Image.BICUBIC, center=(big / 2, big / 2))
    img.alpha_composite(links)
    return img.resize((size, size), Image.LANCZOS)


def main(out: str) -> None:
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        draw(base).save(folder / f"icon_{base}x{base}.png")
        draw(base * 2).save(folder / f"icon_{base}x{base}@2x.png")


if __name__ == "__main__":
    main(sys.argv[1])
