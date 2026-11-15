"""Tests for the reel-script parser that the voiceover and timing tools share."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "invit-analysis-2026" / "voiceover"))

from script_format import parse_sections, parse_sections_text  # noqa: E402

SCRIPT = """# Title

### [0:00–0:08] HOOK
**VO:** "First line,   with   extra spaces."
**On-screen text:** Headline
**Visual:** Stock clip

### [0:08-0:20] POINT ONE
**VO:** "Second line
spans two lines."
**On-screen text:** Point
**Visual:** Chart

### [1:02–1:10] NO VOICE
**On-screen text:** Caption only
**Visual:** Title card
"""


class ParseSectionsTest(unittest.TestCase):
    def test_reads_every_section_with_a_vo_line(self):
        sections = parse_sections_text(SCRIPT)
        self.assertEqual([(s, e) for s, e, _ in sections], [(0, 8), (8, 20)])

    def test_collapses_whitespace_and_keeps_multiline_narration(self):
        sections = parse_sections_text(SCRIPT)
        self.assertEqual(sections[0][2], "First line, with extra spaces.")
        self.assertEqual(sections[1][2], "Second line spans two lines.")

    def test_accepts_hyphen_and_en_dash(self):
        self.assertEqual(len(parse_sections_text(SCRIPT)), 2)

    def test_minutes_are_converted_to_seconds(self):
        text = '### [1:02–1:10] LATE\n**VO:** "Late line."\n'
        self.assertEqual(parse_sections_text(text), [(62, 70, "Late line.")])

    def test_section_without_vo_is_skipped_not_fatal(self):
        text = '### [0:00–0:05] A\n**Visual:** nothing spoken\n### [0:05–0:10] B\n**VO:** "Spoken."\n'
        self.assertEqual(parse_sections_text(text), [(5, 10, "Spoken.")])

    def test_empty_script_gives_no_sections(self):
        self.assertEqual(parse_sections_text("# Nothing here\n"), [])

    def test_reads_from_a_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.md"
            path.write_text(SCRIPT, encoding="utf-8")
            self.assertEqual(parse_sections(path), parse_sections_text(SCRIPT))


if __name__ == "__main__":
    unittest.main()
