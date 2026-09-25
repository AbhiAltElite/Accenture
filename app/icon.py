"""Draw the app icon into a macOS .iconset folder. Called by build_mac_app.sh."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    """Two linked rings on a dark tile: the chain, and nothing else."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.08
    d.rounded_rectangle(
        (pad, pad, size - pad, size - pad), radius=size * 0.2, fill=(15, 23, 42, 255)
    )
    w = max(2, round(size * 0.07))
    r = size * 0.17
    cy = size / 2
    for cx, colour in ((size * 0.40, (56, 139, 253, 255)), (size * 0.60, (210, 153, 34, 255))):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour, width=w)
    return img


def main(out: str) -> None:
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        draw(base).save(folder / f"icon_{base}x{base}.png")
        draw(base * 2).save(folder / f"icon_{base}x{base}@2x.png")


if __name__ == "__main__":
    main(sys.argv[1])
