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
    # Nine additional compositions, not palette-only variants of one plate.
    designs = [
        ("split_interview", "Split interview", 900, "#182235", "#38BDF8"),
        ("ribbon_headline", "Ribbon headline", 150, "#392313", "#FBBF24"),
        ("bracket_quote", "Bracket quote", 420, "#25213D", "#C4B5FD"),
        ("double_pill", "Double pill", 930, "#14352F", "#5EEAD4"),
        ("corner_frame", "Corner frame", 180, "#282B35", "#F9A8D4"),
        ("ticket_announcement", "Ticket announcement", 480, "#332A19", "#FDE68A"),
        ("diagonal_banner", "Diagonal banner", 860, "#182F40", "#7DD3FC"),
        ("stacked_cards", "Stacked cards", 450, "#352032", "#F0ABFC"),
        ("orbit_end_card", "Orbit end card", 820, "#1E3034", "#A7F3D0"),
    ]
    for key, name, top, bg, accent in designs:
        image = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        bottom = top + 244
        if key == "split_interview":
            draw.rectangle((38, top, 526, bottom), fill=bg)
            draw.rectangle((538, top, 682, bottom), fill=accent)
        elif key == "ribbon_headline":
            draw.polygon(
                [
                    (24, top),
                    (696, top),
                    (654, top + 122),
                    (696, bottom),
                    (24, bottom),
                    (62, top + 122),
                ],
                fill=bg,
            )
            draw.line((62, top + 6, 654, top + 6), fill=accent, width=9)
        elif key == "bracket_quote":
            draw.rounded_rectangle((48, top, 672, bottom), radius=16, fill=bg)
            for x, direction in ((36, 1), (684, -1)):
                draw.line(
                    (
                        x + direction * 32,
                        top - 12,
                        x,
                        top - 12,
                        x,
                        bottom + 12,
                        x + direction * 32,
                        bottom + 12,
                    ),
                    fill=accent,
                    width=8,
                )
        elif key == "double_pill":
            draw.rounded_rectangle((40, top, 540, top + 106), radius=48, fill=bg)
            draw.rounded_rectangle((40, top + 118, 540, bottom), radius=48, fill=bg)
            draw.ellipse((548, top + 20, 680, top + 152), fill=accent)
        elif key == "corner_frame":
            draw.rectangle((48, top, 672, bottom), fill=bg)
            draw.line((48, top + 60, 48, top, 160, top), fill=accent, width=12)
            draw.line(
                (560, bottom, 672, bottom, 672, bottom - 60), fill=accent, width=12
            )
        elif key == "ticket_announcement":
            draw.rounded_rectangle((40, top, 680, bottom), radius=20, fill=bg)
            draw.ellipse((22, top + 94, 70, top + 142), fill=(0, 0, 0, 0))
            draw.ellipse((650, top + 94, 698, top + 142), fill=(0, 0, 0, 0))
            for y in range(top + 18, bottom - 12, 22):
                draw.line((530, y, 530, y + 10), fill=accent, width=3)
        elif key == "diagonal_banner":
            draw.polygon(
                [(24, top + 28), (668, top), (696, bottom - 28), (52, bottom)],
                fill=accent,
            )
            draw.polygon(
                [
                    (38, top + 38),
                    (658, top + 16),
                    (680, bottom - 38),
                    (62, bottom - 16),
                ],
                fill=bg,
            )
        elif key == "stacked_cards":
            draw.rounded_rectangle(
                (66, top - 18, 688, bottom - 18), radius=16, fill=accent
            )
            draw.rounded_rectangle((36, top + 8, 658, bottom + 8), radius=16, fill=bg)
        else:
            draw.ellipse((18, top - 38, 702, bottom + 38), outline=accent, width=5)
            draw.rounded_rectangle((48, top, 672, bottom), radius=32, fill=bg)
            draw.ellipse((638, top - 20, 670, top + 12), fill=accent)
        image.save(ROOT / (key + ".png"))
        catalog[key] = {
            "name": name,
            "asset": key + ".png",
            "title_box": [84, top + 36, 420, 70],
            "subtitle_box": [84, top + 142, 420, 70],
            "logo_box": [558, top + 54, 78, 78],
            "title_color": "#FFFFFF",
            "subtitle_color": accent,
        }
    from illustrated_graphic_assets import build_illustrated

    catalog.update(build_illustrated(ROOT))
    from scene_graphic_assets import build_scenes

    catalog.update(build_scenes(ROOT))
    for key, entry in catalog.items():
        pack = {
            "id": key,
            "license": "CC0-1.0",
            "design": entry,
            "defaults": {
                "title": entry["name"],
                "subtitle": "Your subtitle",
                "animation": "fade",
                "duration": 3.0,
            },
            "editable": ["title", "subtitle", "logo"],
            "animations": ["fade", "slide"],
        }
        (ROOT / (key + ".pack.json")).write_text(json.dumps(pack, indent=2) + "\n")
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")


if __name__ == "__main__":
    build()
