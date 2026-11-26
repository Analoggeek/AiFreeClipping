"""Thirty original hand-constructed scene illustrations and editable title plates.

No third-party art. Coordinates are authored here; every scene has a distinct
silhouette. Standalone artwork and panel assets accompany each composed plate.
"""

from PIL import Image, ImageDraw

SCENES = [
    ("film", "Film premiere"),
    ("laptop", "Digital workspace"),
    ("phone", "Mobile story"),
    ("satellite", "Satellite signal"),
    ("robot", "Robot lab"),
    ("battery", "Energy update"),
    ("shield", "Safety notice"),
    ("lock", "Privacy matters"),
    ("key", "Access unlocked"),
    ("compass", "Explore direction"),
    ("globe", "World briefing"),
    ("clock", "Time reminder"),
    ("calendar", "Event calendar"),
    ("trophy", "Winner spotlight"),
    ("dumbbell", "Fitness session"),
    ("football", "Football match"),
    ("basketball", "Basketball court"),
    ("music", "Music release"),
    ("piano", "Piano lesson"),
    ("headphones", "Listening room"),
    ("palette", "Creative studio"),
    ("bulb", "Bright idea"),
    ("umbrella", "Weather update"),
    ("anchor", "Harbor story"),
    ("sailboat", "Ocean journey"),
    ("train", "Rail travel"),
    ("gift", "Gift announcement"),
    ("diamond", "Premium highlight"),
    ("leaf", "Nature note"),
    ("butterfly", "Fresh beginning"),
]


def illustration(name, d, a):
    w = "#F1F5F9"
    b = "#152236"

    def line(points, fill=w, width=9):
        d.line(points, fill=fill, width=width, joint="curve")

    def rect(box, fill=w, r=8):
        d.rounded_rectangle(box, radius=r, fill=fill)

    if name == "film":
        rect((230, 440, 490, 620))
        rect((282, 466, 438, 594), b)
        for x in (244, 460):
            for y in (458, 500, 542, 584):
                rect((x, y, x + 16, y + 18), a, 2)
    elif name == "laptop":
        rect((252, 436, 468, 586))
        rect((266, 450, 454, 568), b)
        d.polygon([(252, 586), (468, 586), (502, 622), (218, 622)], fill=a)
        line((330, 608, 390, 608), b, 5)
    elif name == "phone":
        rect((300, 410, 420, 650), w, 20)
        rect((312, 430, 408, 614), b)
        d.ellipse((350, 624, 370, 644), fill=a)
        line((334, 452, 386, 452), a, 5)
    elif name == "satellite":
        d.polygon([(340, 480), (394, 512), (362, 570), (308, 538)], fill=w)
        for points in (
            [(244, 430), (322, 474), (292, 528), (214, 484)],
            [(410, 524), (488, 568), (458, 622), (380, 578)],
        ):
            d.polygon(points, fill=a)
        line((366, 500, 412, 452))
        d.arc((382, 420, 462, 500), 190, 285, fill=w, width=7)
    elif name == "robot":
        rect((264, 460, 456, 606), w, 24)
        rect((302, 608, 418, 642), a)
        for x in (306, 392):
            d.ellipse((x, 496, x + 24, 520), fill=b)
        line((310, 562, 410, 562), b)
        line((360, 460, 360, 430), a)
        d.ellipse((346, 408, 374, 436), fill=a)
    elif name == "battery":
        rect((234, 474, 474, 602))
        rect((474, 512, 494, 564), a)
        rect((250, 490, 456, 586), b)
        for x in (264, 322, 380):
            rect((x, 502, x + 40, 574), a, 3)
    elif name == "shield":
        d.polygon(
            [
                (360, 420),
                (466, 464),
                (450, 574),
                (412, 620),
                (360, 654),
                (308, 620),
                (270, 574),
                (254, 464),
            ],
            fill=w,
        )
        line((306, 526, 346, 570, 418, 482), a, 18)
    elif name == "lock":
        d.arc((292, 420, 428, 568), 180, 360, fill=w, width=18)
        rect((272, 508, 448, 640), a, 18)
        d.ellipse((346, 544, 374, 572), fill=b)
        rect((354, 562, 366, 602), b, 3)
    elif name == "key":
        d.ellipse((234, 448, 350, 564), outline=w, width=20)
        line((332, 544, 468, 636), a, 22)
        line((414, 592, 438, 566), a, 16)
        line((450, 616, 474, 590), a, 16)
    elif name == "compass":
        d.ellipse((248, 428, 472, 652), outline=w, width=10)
        d.polygon([(398, 468), (376, 558), (322, 612), (344, 522)], fill=a)
        d.polygon([(398, 468), (344, 522), (360, 540)], fill=w)
    elif name == "globe":
        d.ellipse((248, 428, 472, 652), outline=w, width=9)
        d.ellipse((302, 428, 418, 652), outline=a, width=7)
        for y in (488, 540, 592):
            line((260, y, 460, y), a, 6)
        line((360, 434, 360, 646), w, 6)
    elif name == "clock":
        d.ellipse((248, 428, 472, 652), outline=w, width=12)
        line((360, 460, 360, 540, 418, 572), a, 12)
        for x, y in ((354, 442), (354, 620), (266, 534), (442, 534)):
            rect((x, y, x + 10, y + 10), w, 2)
    elif name == "calendar":
        rect((250, 446, 470, 636))
        rect((250, 446, 470, 492), a)
        for x in (290, 418):
            line((x, 426, x, 466), w, 10)
        for x in (278, 334, 390):
            for y in (518, 570):
                rect((x, y, x + 28, y + 26), b, 3)
    elif name == "trophy":
        d.polygon(
            [(286, 434), (434, 434), (422, 542), (394, 576), (326, 576), (298, 542)],
            fill=a,
        )
        d.arc((244, 452, 320, 546), 70, 280, fill=w, width=10)
        d.arc((400, 452, 476, 546), 260, 110, fill=w, width=10)
        rect((348, 572, 372, 620))
        rect((304, 620, 416, 642), a)
    elif name == "dumbbell":
        line((250, 540, 470, 540), w, 18)
        for x, h in ((242, 54), (274, 84), (422, 84), (454, 54)):
            rect((x, 540 - h, x + 24, 540 + h), a)
    elif name == "football":
        d.ellipse((248, 428, 472, 652), fill=w)
        d.polygon([(360, 494), (402, 526), (386, 576), (334, 576), (318, 526)], fill=b)
        for points in (
            (360, 434, 360, 494),
            (260, 500, 318, 526),
            (460, 500, 402, 526),
            (294, 624, 334, 576),
            (426, 624, 386, 576),
        ):
            line(points, b, 8)
    elif name == "basketball":
        d.ellipse((248, 428, 472, 652), fill=a, outline=w, width=8)
        line((250, 540, 470, 540), b, 7)
        line((360, 432, 360, 648), b, 7)
        d.arc((180, 432, 342, 648), 280, 80, fill=b, width=7)
        d.arc((378, 432, 540, 648), 100, 260, fill=b, width=7)
    elif name == "music":
        line((324, 594, 324, 454, 432, 432, 432, 572), w, 14)
        line((324, 480, 432, 458), a, 18)
        d.ellipse((268, 572, 326, 618), fill=a)
        d.ellipse((376, 550, 434, 596), fill=a)
    elif name == "piano":
        rect((238, 464, 482, 616), w)
        for x in range(272, 480, 34):
            line((x, 468, x, 612), b, 3)
        for x in (260, 294, 362, 396, 430):
            rect((x, 466, x + 20, 550), b, 2)
    elif name == "headphones":
        d.arc((256, 432, 464, 642), 180, 360, fill=w, width=18)
        rect((244, 526, 298, 622), a, 20)
        rect((422, 526, 476, 622), a, 20)
    elif name == "palette":
        d.ellipse((244, 438, 476, 644), fill=w)
        d.ellipse((388, 560, 458, 630), fill=b)
        for x, y, color in (
            (282, 482, a),
            (344, 464, "#FCA5A5"),
            (402, 492, "#93C5FD"),
            (292, 560, "#FDE68A"),
        ):
            d.ellipse((x - 14, y - 14, x + 14, y + 14), fill=color)
    elif name == "bulb":
        d.ellipse((288, 428, 432, 572), fill=a)
        rect((326, 550, 394, 610))
        rect((336, 612, 384, 630), a)
        for points in (
            (360, 396, 360, 416),
            (250, 456, 270, 470),
            (450, 470, 470, 456),
            (244, 530, 268, 530),
            (452, 530, 476, 530),
        ):
            line(points, w, 7)
    elif name == "umbrella":
        d.pieslice((246, 426, 474, 650), 180, 360, fill=a)
        line((360, 538, 360, 614), w, 10)
        d.arc((320, 592, 360, 644), 0, 180, fill=w, width=10)
        d.arc((290, 426, 430, 650), 180, 360, fill=w, width=5)
    elif name == "anchor":
        d.ellipse((334, 430, 386, 482), outline=w, width=9)
        line((360, 482, 360, 634), w, 12)
        line((298, 512, 422, 512), a, 10)
        d.arc((264, 492, 456, 642), 0, 180, fill=w, width=12)
        d.polygon([(260, 548), (284, 574), (256, 580)], fill=a)
        d.polygon([(460, 548), (436, 574), (464, 580)], fill=a)
    elif name == "sailboat":
        line((360, 422, 360, 590), w, 8)
        d.polygon([(348, 440), (348, 574), (258, 574)], fill=a)
        d.polygon([(374, 454), (374, 574), (454, 574)], fill=w)
        d.polygon([(244, 592), (476, 592), (442, 636), (278, 636)], fill=a)
    elif name == "train":
        rect((278, 428, 442, 614), w, 24)
        rect((296, 454, 424, 524), b)
        for x in (302, 394):
            d.ellipse((x, 550, x + 24, 574), fill=a)
        line((306, 610, 282, 648), a, 10)
        line((414, 610, 438, 648), a, 10)
        line((294, 630, 426, 630), w, 6)
    elif name == "gift":
        rect((256, 500, 464, 634), a)
        rect((244, 474, 476, 510), w)
        rect((348, 474, 372, 634), w, 0)
        d.ellipse((296, 422, 360, 474), outline=a, width=10)
        d.ellipse((360, 422, 424, 474), outline=a, width=10)
    elif name == "diamond":
        d.polygon([(286, 452), (434, 452), (486, 516), (360, 646), (234, 516)], fill=a)
        line((234, 516, 486, 516), w, 6)
        line((286, 452, 316, 516, 360, 646, 404, 516, 434, 452), w, 6)
        line((316, 516, 360, 452, 404, 516), w, 5)
    elif name == "leaf":
        d.ellipse((270, 426, 450, 636), fill=a)
        line((286, 650, 406, 460), w, 9)
        for points in (
            (326, 584, 300, 526),
            (350, 544, 414, 526),
            (372, 508, 346, 470),
        ):
            line(points, w, 6)
    else:
        for box in (
            (248, 440, 358, 560),
            (362, 440, 472, 560),
            (270, 550, 358, 640),
            (362, 550, 450, 640),
        ):
            d.ellipse(box, fill=a)
        line((360, 472, 360, 636), w, 12)
        line((360, 480, 336, 450), w, 5)
        line((360, 480, 384, 450), w, 5)


def build_scenes(root):
    catalog = {}
    for index, (name, title) in enumerate(SCENES):
        key = "scene_" + name
        accent = ("#93C5FD", "#6EE7B7", "#FDE68A")[index % 3]
        art = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
        illustration(name, ImageDraw.Draw(art), accent)
        art.save(root / (key + ".art.png"))
        panel = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
        d = ImageDraw.Draw(panel)
        # Three functional layouts, each with safe, nonoverlapping editable slots.
        top = (870, 780, 950)[index % 3]
        bg = "#152236"
        if index % 3 == 0:
            d.rounded_rectangle((36, top, 684, top + 240), radius=24, fill=bg)
            d.rectangle((36, top, 48, top + 240), fill=accent)
        elif index % 3 == 1:
            d.polygon(
                [(36, top), (660, top), (684, top + 240), (60, top + 240)], fill=bg
            )
            d.line((60, top + 232, 678, top + 232), fill=accent, width=8)
        else:
            d.rounded_rectangle((36, top, 528, top + 112), radius=18, fill=bg)
            d.rounded_rectangle((36, top + 124, 528, top + 240), radius=18, fill=bg)
            d.rounded_rectangle(
                (544, top, 684, top + 140), radius=24, fill=bg, outline=accent, width=4
            )
        panel.save(root / (key + ".panel.png"))
        plate = panel.copy()
        plate.alpha_composite(art)
        plate.save(root / (key + ".png"))
        catalog[key] = {
            "name": title,
            "asset": key + ".png",
            "artwork": key + ".art.png",
            "panel": key + ".panel.png",
            "category": "Original illustrated scenes",
            "title_box": [76, top + 30, 432, 70],
            "subtitle_box": [76, top + 148, 432, 60],
            "logo_box": [564, top + 24, 88, 88],
            "title_color": "#F1F5F9",
            "subtitle_color": accent,
        }
    return catalog
