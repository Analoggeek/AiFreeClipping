"""Rebuild the repository's original geometric RGBA motion-graphic plates."""

from pathlib import Path
import json
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "resources/templates/motion"


def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    specs = [
        ("slate_lower_third", "Slate lower third", (920, 1160), "#172236", "#818CF8"),
        ("coral_callout", "Coral callout", (180, 440), "#351E29", "#FB7185"),
        ("mint_end_card", "Mint end card", (450, 830), "#12372F", "#6EE7B7"),
    ]
    catalog = {}
    for key, name, (top, bottom), background, accent in specs:
        image = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((48, top, 672, bottom), radius=24, fill=background)
        draw.rectangle((48, top + 24, 58, bottom - 24), fill=accent)
        draw.polygon([(620, top), (672, top), (672, top + 52)], fill=accent)
        image.save(ROOT / (key + ".png"))
        catalog[key] = {
            "name": name,
            "asset": key + ".png",
            "title_box": [84, top + 42, 440, 70],
            "subtitle_box": [84, top + 124, 440, 70],
            "logo_box": [548, top + 48, 88, 88],
            "title_color": "#FFFFFF",
            "subtitle_color": accent,
        }
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")


if __name__ == "__main__":
    build()
