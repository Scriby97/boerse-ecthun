"""Erzeugt das App-Icon im Mac-Stil aus dem Club-Logo: weisse Kachel mit runden Ecken und leichtem Schatten.

Masse nach Apples Icon-Raster: 1024 × 1024 Fläche, Kachel 824 × 824, Eckradius 185.
Aufruf: python scripts/app_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "inventar" / "assets"
SIZE, TILE, RADIUS, LOGO = 1024, 824, 185, 660


def main():
    offset = (SIZE - TILE) // 2
    box = (offset, offset, offset + TILE, offset + TILE)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, RADIUS, fill=255)

    shadow = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 12, box[2], box[3] + 12), RADIUS, fill=90)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.putalpha(shadow.filter(ImageFilter.GaussianBlur(14)))

    tile = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    logo = Image.open(ASSETS / "logo-ec-thun.png").convert("RGBA")
    scale = LOGO / max(logo.size)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    tile.paste(logo, ((SIZE - logo.width) // 2, (SIZE - logo.height) // 2), logo)
    icon.paste(tile, (0, 0), mask)
    icon.save(ASSETS / "app-icon.png")


if __name__ == "__main__":
    main()
