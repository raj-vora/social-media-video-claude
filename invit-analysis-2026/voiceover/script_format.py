"""Parse the reel-script format that the voiceover and timing tools depend on.

A script is a Markdown file whose sections look like this:

    ### [0:00–0:12] TITLE
    **VO:** "The line the narrator reads."
    **On-screen text:** ...
    **Visual:** ...

This module has no heavy dependencies, so tests and light tools can import it
without loading the TTS stack.
"""

import re
from pathlib import Path

# Section header: "### [m:ss–m:ss]" with an en dash or a hyphen between the times.
SECTION_RE = re.compile(r"^### \[(\d+):(\d+)[–-](\d+):(\d+)\]", re.M)
# The single narration line of a section. DOTALL lets a quoted line span newlines.
VO_RE = re.compile(r'^\*\*VO:\*\*\s*"(.*?)"\s*$', re.M | re.S)


def parse_sections(path: Path) -> list[tuple[int, int, str]]:
    """Return ``(start_sec, end_sec, vo_text)`` for each section, in script order.

    Sections without a ``**VO:**`` line are skipped. Whitespace inside the
    narration is collapsed to single spaces.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_sections_text(text)


def parse_sections_text(text: str) -> list[tuple[int, int, str]]:
    """Same as :func:`parse_sections`, for script text already in memory."""
    heads = list(SECTION_RE.finditer(text))
    sections = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        vo = VO_RE.search(text[head.end():end])
        if not vo:
            continue
        m1, s1, m2, s2 = map(int, head.groups())
        sections.append((m1 * 60 + s1, m2 * 60 + s2, " ".join(vo.group(1).split())))
    return sections
