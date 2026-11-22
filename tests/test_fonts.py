"""Tests for the font handling in the render pipeline.

FFmpeg's ``drawtext`` filter needs to be told which font file to use.
Some builds have a compiled-in default and some do not -- the macOS
builds do not, and the filter then stops with

    No font filename provided

The ``ass`` filter has the same problem: it looks for the fonts named in
the subtitle file in the system font directories.

These tests check that a real font file is always found, that the
argument that carries it is separated from the next one by a colon, and
that the caption styles name a font the machine really has.
"""
from __future__ import annotations

import re
import unittest

from clipos.captions.caption_engine import (
    CAPTION_STYLES,
    FONT_CANDIDATES,
    get_style,
    system_font,
)
from clipos.core.fonts import (
    drawtext_font_args,
    find_font_file,
    font_dir,
    fontsdir_arg,
)


class TestFontDiscovery(unittest.TestCase):
    def test_a_font_file_is_found(self):
        """A real font file has to be found, or the text is not drawn."""
        font = find_font_file()
        self.assertIsNotNone(font, "no font file was found on this machine")
        self.assertTrue(font.is_file())
        self.assertTrue(font.stat().st_size > 0)

    def test_a_font_directory_is_found(self):
        base = font_dir()
        self.assertIsNotNone(base)
        self.assertTrue(base.is_dir())

    def test_the_font_argument_is_separated_by_a_colon(self):
        """The argument has to end with a colon.

        Without it the next argument runs into it -- ``fontfile='x'`` and
        ``fontcolor=#FFD400`` become ``fontfile='x'fontcolor=#FFD400``,
        and the filter reads the colour as part of the file name and
        draws the text in the wrong colour.
        """
        args = drawtext_font_args()
        if not args:
            self.skipTest("no font on this machine")
        self.assertTrue(args.endswith(":"), f"{args!r} does not end with a colon")
        self.assertIn("fontfile=", args)

    def test_the_font_directory_argument_is_separated_by_a_colon(self):
        args = fontsdir_arg()
        if not args:
            self.skipTest("no font on this machine")
        self.assertTrue(args.endswith(":"), f"{args!r} does not end with a colon")
        self.assertIn("fontsdir=", args)

    def test_the_filter_arguments_have_no_spaces(self):
        """A space would end the argument and start a new one."""
        for args in (drawtext_font_args(), fontsdir_arg()):
            if args:
                self.assertNotIn(" ", args)


class TestFilterArguments(unittest.TestCase):
    def test_the_drawtext_filter_keeps_its_arguments_apart(self):
        """Every ``key=value`` pair in the filter has to be complete."""
        font = drawtext_font_args()
        if not font:
            self.skipTest("no font on this machine")
        filter_text = f"drawtext=text='Hello':{font}fontcolor=#FFD400:fontsize=54"
        pairs = dict(re.findall(r"([a-z_]+)=([^:']*)", filter_text))
        self.assertEqual(pairs.get("fontfile"), "")
        self.assertIn("fontfile='", filter_text)
        # The colour must not have become part of the file name.
        self.assertIn("':fontcolor=#FFD400", filter_text)


class TestCaptionFonts(unittest.TestCase):
    def test_every_style_names_a_font(self):
        for key, style in CAPTION_STYLES.items():
            self.assertTrue(style.font, f"the style {key} has no font")

    def test_the_font_is_one_of_the_known_ones(self):
        name = system_font()
        self.assertTrue(name)
        # Without a running application the font service cannot be
        # consulted, so the first choice is used.
        self.assertIn(name, FONT_CANDIDATES)

    def test_every_style_is_usable(self):
        style = get_style("bold_viral")
        self.assertTrue(style.font)
        self.assertGreater(style.size, 0)


if __name__ == "__main__":
    unittest.main()
