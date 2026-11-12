"""Draw the app's mark (user 2026-10-30: the small window showed Tk's lone feather, other apps
their own marks): an annotation box, white with a handle at each corner, on a rounded square of
the app's indigo (index.css --action). Written to agent_app/agent_app/icon.ico (every size
Windows asks for: the small window, the taskbar, the shortcut), icon.png (the small window
elsewhere) and ui/public/icon.png (the page's mark: the app's window shows it in the taskbar).
Run again only when the mark changes:

    uv run --project agent_app python agent_app/tools/handout/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

PACKAGE = Path(__file__).resolve().parents[2] / "agent_app"
INDIGO = (91, 63, 214, 255)  # --action, light
WHITE = (255, 255, 255, 255)
SIDE = 256


def mark(side=SIDE):
    """The mark at one size, drawn large and made smaller so its edges are smooth."""
    big = side * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=INDIGO)
    left, top, right, bottom = big * 0.24, big * 0.28, big * 0.76, big * 0.72
    draw.rectangle((left, top, right, bottom), outline=WHITE, width=round(big * 0.055))
    handle = big * 0.075
    for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
        draw.rectangle((x - handle, y - handle, x + handle, y + handle), fill=WHITE)
    return image.resize((side, side), Image.LANCZOS)


def main():
    image = mark()
    image.save(PACKAGE / "icon.png")
    image.save(PACKAGE.parent / "ui/public/icon.png")
    sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    # BMP inside, as Windows' own icons are (2026-10-30: the PNG Pillow writes by default came out
    # broken where Windows read the shortcut's icon at 48 px).
    image.save(PACKAGE / "icon.ico", sizes=sizes, bitmap_format="bmp")
    print(PACKAGE / "icon.ico", PACKAGE / "icon.png")


if __name__ == "__main__":
    main()
