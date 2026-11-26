"""Eight original illustrated title scenes; no downloaded or third-party art."""

from PIL import Image, ImageDraw


def build_illustrated(root):
    catalog = {}
    scenes = [
        ("launch_rocket", "Launch / rocket", "#93C5FD"),
        ("learning_book", "Learning / book", "#FDE68A"),
        ("podcast_microphone", "Podcast / microphone", "#F9A8D4"),
        ("growth_chart", "Growth / chart", "#6EE7B7"),
        ("travel_mountains", "Travel / mountains", "#7DD3FC"),
        ("kitchen_chef", "Kitchen / chef", "#FDBA74"),
        ("gaming_controller", "Gaming / controller", "#C4B5FD"),
        ("science_microscope", "Science / microscope", "#67E8F9"),
    ]
    for key, name, accent in scenes:
        image = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        bg = "#152236"
        ink = "#F1F5F9"
        # Illustration medallion stays separate from user text and logo slots.
        d.ellipse((190, 370, 530, 710), fill=bg, outline=accent, width=5)
        if key == "launch_rocket":
            d.polygon(
                [(360, 405), (408, 478), (408, 578), (312, 578), (312, 478)], fill=ink
            )
            d.ellipse((338, 465, 382, 509), fill=accent)
            d.polygon([(312, 518), (282, 594), (312, 578)], fill=accent)
            d.polygon([(408, 518), (438, 594), (408, 578)], fill=accent)
            d.polygon([(330, 586), (360, 660), (390, 586)], fill=accent)
        elif key == "learning_book":
            d.polygon(
                [
                    (240, 448),
                    (330, 448),
                    (360, 470),
                    (390, 448),
                    (480, 448),
                    (480, 624),
                    (390, 624),
                    (360, 646),
                    (330, 624),
                    (240, 624),
                ],
                fill=ink,
            )
            d.line((360, 474, 360, 630), fill=bg, width=5)
            for y in (482, 510, 538, 566, 594):
                d.line((256, y, 328, y), fill=accent, width=5)
                d.line((390, y, 462, y), fill=bg, width=3)
        elif key == "podcast_microphone":
            d.rounded_rectangle((326, 430, 394, 572), radius=32, fill=ink)
            d.arc((302, 490, 418, 608), 0, 180, fill=accent, width=10)
            d.line((360, 608, 360, 640), fill=ink, width=10)
            d.line((320, 644, 400, 644), fill=ink, width=10)
            for x, offset in ((260, 0), (444, 0), (282, 18), (422, 18)):
                d.line((x, 490 + offset, x, 565 - offset), fill=accent, width=7)
        elif key == "growth_chart":
            d.line((248, 434, 248, 632, 486, 632), fill=ink, width=6)
            for x, h in ((280, 64), (338, 110), (396, 164)):
                d.rounded_rectangle((x, 620 - h, x + 34, 620), radius=5, fill=accent)
            d.line((270, 510, 326, 480, 382, 460, 458, 422), fill=ink, width=7)
            d.polygon([(436, 420), (466, 414), (462, 446)], fill=ink)
        elif key == "travel_mountains":
            d.ellipse((400, 420, 460, 480), fill=accent)
            d.polygon([(220, 622), (320, 452), (416, 622)], fill=ink)
            d.polygon([(320, 452), (284, 514), (324, 498), (352, 514)], fill=accent)
            d.polygon([(324, 622), (420, 492), (510, 622)], fill=accent)
            d.line((254, 646, 472, 646), fill=ink, width=5)
        elif key == "kitchen_chef":
            d.ellipse((264, 446, 360, 542), fill=ink)
            d.ellipse((316, 416, 412, 526), fill=ink)
            d.ellipse((370, 446, 466, 542), fill=ink)
            d.polygon([(290, 500), (438, 500), (422, 596), (306, 596)], fill=ink)
            d.rectangle((302, 580, 426, 612), fill=accent)
            for x in (330, 360, 390):
                d.line((x, 526, x, 566), fill=bg, width=4)
        elif key == "gaming_controller":
            d.rounded_rectangle((236, 476, 484, 610), radius=46, fill=ink)
            d.rectangle((270, 520, 326, 536), fill=bg)
            d.rectangle((290, 500, 306, 556), fill=bg)
            for x, y in ((428, 510), (450, 532), (406, 532), (428, 554)):
                d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=accent)
            d.line((340, 492, 380, 492), fill=bg, width=4)
        else:
            d.rounded_rectangle((324, 430, 366, 530), radius=8, fill=ink)
            d.rectangle((330, 524, 360, 546), fill=accent)
            d.arc((304, 450, 450, 626), 270, 90, fill=ink, width=16)
            d.line((284, 562, 390, 562), fill=accent, width=9)
            d.line((360, 620, 360, 646), fill=ink, width=12)
            d.rounded_rectangle((286, 640, 448, 658), radius=6, fill=ink)
            d.ellipse((326, 574, 354, 602), fill=accent)
        # Multi-component plate: title header, subtitle strip and separate logo badge.
        d.rounded_rectangle((40, 850, 680, 1100), radius=24, fill=bg)
        d.rectangle((40, 850, 680, 860), fill=accent)
        d.rounded_rectangle((64, 984, 526, 1076), radius=12, fill="#23354D")
        d.rounded_rectangle((544, 900, 656, 1012), radius=18, outline=accent, width=4)
        image.save(root / (key + ".png"))
        catalog[key] = {
            "name": name,
            "asset": key + ".png",
            "title_box": [80, 892, 438, 70],
            "subtitle_box": [80, 1004, 422, 60],
            "logo_box": [556, 912, 88, 88],
            "title_color": ink,
            "subtitle_color": accent,
            "category": "Illustrated scenes",
        }
    return catalog
