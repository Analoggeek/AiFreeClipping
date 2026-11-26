"""Fifty original palette/typography/motion compositions, no external assets.

These are combinations of five implemented motion treatments and ten visual
families, not fifty different animation algorithms or copied branded presets.
"""

FAMILIES = (
    ("creator", "Creator Signal", "#FFFFFF", "#FFD34E", 6.0, True),
    ("cinema", "Cinema Paper", "#F1EBDD", "#E6BE78", 2.0, False),
    ("gaming", "Arcade Current", "#94FFF0", "#FF70C8", 4.0, True),
    ("professional", "Office Slate", "#F5F7FF", "#93C5FD", 2.0, False),
    ("social", "Social Coral", "#FFE9E3", "#FF907A", 5.0, True),
    ("typography", "Type Structure", "#FFF4C7", "#9AD7FF", 3.0, True),
    ("hindi", "Devanagari Clear", "#FFFFFF", "#FFCB80", 4.0, False),
    ("podcast", "Conversation Mint", "#E3FFF1", "#78DCB1", 3.0, False),
    ("documentary", "Field Journal", "#ECE9DC", "#DDBE79", 2.0, False),
    ("education", "Lesson Azure", "#E7F3FF", "#70BBFF", 3.0, True),
)
TREATMENTS = (
    ("clear", "Clear", "none", 50, False),
    ("rise", "Rise", "slide_up", 54, False),
    ("pulse", "Pulse", "pop", 60, True),
    ("reveal", "Word Reveal", "word_reveal", 54, False),
    ("focus", "Focus", "blur_reveal", 52, False),
)


def register_original_styles(register, style_class, font):
    from .customization import ass_color

    for family, name, primary, highlight, stroke, bold in FAMILIES:
        for treatment, title, animation, size, uppercase in TREATMENTS:
            register(
                style_class(
                    key=f"original_{family}_{treatment}",
                    name=f"{name} · {title}",
                    description=f"Original {family} palette with {animation} motion; uses installed fonts.",
                    font=font,
                    size=size,
                    bold=bold,
                    uppercase=uppercase,
                    primary_color=ass_color(primary),
                    highlight_color=ass_color(highlight),
                    outline_color="&H00000000",
                    stroke_width=stroke,
                    shadow=1.5,
                    margin_v=220,
                    animation=animation,
                )
            )


def original_style_keys():
    return [
        f"original_{family}_{treatment}"
        for family, *_ in FAMILIES
        for treatment, *_ in TREATMENTS
    ]
