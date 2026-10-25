"""Hintergrundbild für das Installationsfenster (DMG): Pfeil von der App zu «Programme» und ein kurzer Hinweis.

Erzeugt scripts/dmg/background.png (600 × 400) und background@2x.png (für Retina-Bildschirme).
Die Symbole setzt scripts/dmg_settings.py auf (150, 190) und (450, 190); der Pfeil liegt dazwischen.
Aufruf: python scripts/dmg_background.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TARGET = Path(__file__).resolve().parent / "dmg"
WIDTH, HEIGHT = 600, 400
NAVY = (12, 35, 92)
ARROW = (148, 163, 184)
MUTED = (100, 116, 139)
FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
BOLD_FONTS = ["/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arialbd.ttf"]


def font(size: int, bold: bool = False):
    for path in BOLD_FONTS if bold else FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=1 if bold and path.endswith(".ttc") else 0)
    return ImageFont.load_default(size)


def draw(scale: int) -> Image.Image:
    s = scale
    image = Image.new("RGB", (WIDTH * s, HEIGHT * s), (248, 250, 252))
    d = ImageDraw.Draw(image)
    # Pfeil zwischen den Symbolen (Mitte y = 190, Symbole 128 px breit)
    y, left, right = 182 * s, 236 * s, 362 * s
    d.line([(left, y), (right - 22 * s, y)], fill=ARROW, width=10 * s)
    d.polygon([(right, y), (right - 30 * s, y - 22 * s), (right - 30 * s, y + 22 * s)], fill=ARROW)

    def centered(text, top, size, color, bold=False):
        f = font(size * s, bold)
        width = d.textlength(text, font=f)
        d.text(((WIDTH * s - width) / 2, top * s), text, font=f, fill=color)

    centered("Börse EC Thun installieren", 32, 22, NAVY, bold=True)
    centered("Die App mit der Maus auf «Programme» ziehen.", 300, 15, MUTED)
    centered("Danach dieses Fenster schliessen und die App im Ordner Programme öffnen.", 324, 12, MUTED)
    return image


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    draw(1).save(TARGET / "background.png")
    draw(2).save(TARGET / "background@2x.png")


if __name__ == "__main__":
    main()
