"""Deterministic worship-slide segmentation.

Goals (in order): never change the authorized words, keep natural sung
phrases together, prefer 1-2 lines per slide, allow 3 when it reads better,
flag anything that needs a human look.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import MusicalPhrase, SlideCue, Song, SongPlan, ThemeReference
from .parser import strip_repeat_marker

# Words a singer naturally breathes before when a long line must wrap.
BREAK_BEFORE = {
    "and", "but", "for", "cause", "'cause", "when", "where", "while", "till", "until", "as",
    "that", "who", "with", "to", "from", "through", "in", "on", "my", "your", "our",
    "y", "que", "pero", "porque", "cuando", "con", "en", "por", "mi", "tu",
}


@dataclass
class SegmentOptions:
    max_lines_per_slide: int = 2  # 1 or 2 normally; 3/4 allowed but flagged
    max_line_chars: int = 38  # longest line that reads well at the theme's font size
    max_slide_chars: int = 84  # total characters before a slide feels crowded
    allow_three_line_slides: bool = True
    short_line_chars: int = 14  # lines this short can stack three to a slide


def split_long_line(line: str, max_chars: int) -> list[str]:
    """Split a sung line that is too long for one display line at a natural point.

    Splits happen only between words. Preference: after punctuation, then
    before a conjunction/preposition, closest to the middle.
    """
    if len(line) <= max_chars:
        return [line]
    words = line.split(" ")
    if len(words) < 2:
        return [line]
    best = None
    best_score = None
    total = len(line)
    for i in range(1, len(words)):
        left = " ".join(words[:i])
        right = " ".join(words[i:])
        balance = abs(len(left) - len(right)) / total
        score = balance
        if re.search(r"[,;:—–-]$", left):
            score -= 0.35
        elif re.search(r"[.!?]$", left):
            score -= 0.45
        elif words[i].lower().strip("\"'(") in BREAK_BEFORE:
            score -= 0.2
        if len(left) > max_chars or len(right) > max_chars:
            score += 0.5  # still allowed, but recursion will split further
        if len(words[i - 1]) <= 2 and words[i - 1].lower() in {"a", "an", "the", "o", "oh", "my", "el", "la"}:
            score += 0.6  # never strand an article at the end of a line
        if best_score is None or score < best_score:
            best, best_score = i, score
    assert best is not None
    left = " ".join(words[:best])
    right = " ".join(words[best:])
    return split_long_line(left, max_chars) + split_long_line(right, max_chars)


def _chunk_stanza(lines: list[tuple[str, str | None]], opt: SegmentOptions) -> list[list[tuple[str, str | None]]]:
    n = len(lines)
    if n == 0:
        return []
    per = max(1, opt.max_lines_per_slide)
    slides: list[list[tuple[str, str | None]]] = []
    i = 0
    while i < n:
        remaining = n - i
        take = min(per, remaining)
        # If taking `per` would leave exactly one orphan line, consider a three-line slide.
        if per == 2 and remaining == 3 and opt.allow_three_line_slides:
            trio = lines[i : i + 3]
            chars = sum(len(t[0]) for t in trio)
            if chars <= opt.max_slide_chars and all(len(t[0]) <= opt.max_line_chars for t in trio):
                take = 3
        # Stack very short lines (e.g. "Holy, holy") three to a slide when it fits.
        if per == 2 and take == 2 and remaining >= 3 and opt.allow_three_line_slides:
            trio = lines[i : i + 3]
            if all(len(t[0]) <= opt.short_line_chars for t in trio) and (remaining - 3) != 1:
                take = 3
        # Don't let a slide exceed the character budget: fall back to fewer lines.
        while take > 1 and sum(len(t[0]) for t in lines[i : i + take]) > opt.max_slide_chars + 10:
            take -= 1
        slides.append(lines[i : i + take])
        i += take
    return slides


def segment_song(song: Song, opt: SegmentOptions | None = None, theme: ThemeReference | None = None) -> SongPlan:
    opt = opt or SegmentOptions()
    cues: list[SlideCue] = []
    for sec in song.sections:
        sec.phrases = []
        if sec.instrumental or not sec.source_lines:
            cues.append(SlideCue(section=sec.name, index_in_section=0, lines=[], flags=["instrumental_blank"]))
            continue
        # Stanzas are separated by explicit blank lines in the source.
        bounds = [0] + sorted(set(b for b in sec.explicit_breaks if 0 < b < len(sec.source_lines))) + [len(sec.source_lines)]
        idx = 0
        for a, b in zip(bounds, bounds[1:]):
            display: list[tuple[str, str | None]] = []
            line_flags: list[list[str]] = []
            for li in range(a, b):
                src = sec.source_lines[li]
                tr = sec.translation_lines[li] if li < len(sec.translation_lines) else None
                shown, marker = strip_repeat_marker(src)
                lf: list[str] = []
                if marker:
                    lf.append(f"repeat_marker_removed:{marker}")
                pieces = split_long_line(shown, opt.max_line_chars) if not tr else [shown]
                if len(pieces) > 1:
                    lf.append("long_line_wrapped")
                for p in pieces:
                    sec.phrases.append(MusicalPhrase(text=p, translation=tr, source_line_index=li))
                    display.append((p, tr))
                    line_flags.append(lf)
            pos = 0
            for chunk in _chunk_stanza(display, opt):
                flags = list(dict.fromkeys(f for fl in line_flags[pos : pos + len(chunk)] for f in fl))
                pos += len(chunk)
                if len(chunk) == 3:
                    flags.append("three_lines")
                if len(chunk) >= 4:
                    flags.append("four_lines_review")
                if any(len(t[0]) > opt.max_line_chars for t in chunk):
                    flags.append("line_too_long")
                cues.append(
                    SlideCue(
                        section=sec.name,
                        index_in_section=idx,
                        lines=[t[0] for t in chunk],
                        translation_lines=[t[1] for t in chunk if t[1]],
                        flags=flags,
                    )
                )
                idx += 1
    return SongPlan(song=song, cues=cues, theme=theme or ThemeReference())
