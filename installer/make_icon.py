"""Write the detectTOL shortcut icon (a blue square with a white plus/minus sign).

Usage: python make_icon.py <out.ico>   (needs pillow; part of the app environment)
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw


def main(path: str) -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, size - 8, size - 8), radius=44, fill=(31, 111, 235, 255))
    w = 22
    cx = size // 2
    d.rectangle((cx - 70, 96 - w // 2, cx + 70, 96 + w // 2), fill="white")  # plus: bar
    d.rectangle((cx - w // 2, 26, cx + w // 2, 166), fill="white")  # plus: stem
    d.rectangle((cx - 70, 206 - w // 2, cx + 70, 206 + w // 2), fill="white")  # minus
    img.save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main(sys.argv[1])
