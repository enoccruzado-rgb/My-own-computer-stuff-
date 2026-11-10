"""Arrangement parsing: "V1, C, V2, C, B x2, C, Tag" -> Arrangement."""
from __future__ import annotations

import difflib
import re

from .models import Arrangement, RepeatInstruction, Song

ABBREVIATIONS = {
    "v": "Verse", "vs": "Verse", "verse": "Verse", "verso": "Verse",
    "c": "Chorus", "ch": "Chorus", "cho": "Chorus", "chorus": "Chorus", "coro": "Chorus",
    "pc": "Pre-Chorus", "pre": "Pre-Chorus", "prechorus": "Pre-Chorus", "pre-chorus": "Pre-Chorus",
    "post": "Post-Chorus", "postchorus": "Post-Chorus", "post-chorus": "Post-Chorus",
    "b": "Bridge", "br": "Bridge", "bridge": "Bridge", "puente": "Bridge",
    "t": "Tag", "tag": "Tag",
    "i": "Intro", "in": "Intro", "intro": "Intro",
    "o": "Outro", "out": "Outro", "outro": "Outro",
    "e": "Ending", "end": "Ending", "ending": "Ending",
    "inst": "Instrumental", "instrumental": "Instrumental",
    "int": "Interlude", "interlude": "Interlude",
    "vamp": "Vamp", "refrain": "Refrain", "blank": "Blank",
}

_TOKEN = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z\- ]*?)\s*(?P<num>\d+)?\s*(?:(?:x|\*)\s*(?P<rep>\d+)|\((?P<rep2>\d+)\s*x\)|(?P<rep3>\d+)x)?\s*(?:\[(?P<note>[^\]]*)\])?$",
    re.I,
)


class ArrangementError(ValueError):
    pass


def _resolve(name: str, num: str | None, song: Song) -> str:
    key = name.strip().lower().replace(" ", "")
    canon = ABBREVIATIONS.get(key)
    candidates = [s.name for s in song.sections]
    if canon is None:
        # Allow a full section name written out, e.g. "Chorus 2" handled above; try direct.
        direct = f"{name.strip()} {num}".strip() if num else name.strip()
        for c in candidates:
            if c.lower() == direct.lower():
                return c
        hint = difflib.get_close_matches(direct, candidates, n=1)
        raise ArrangementError(f"unknown section {direct!r}" + (f" (did you mean {hint[0]!r}?)" if hint else ""))
    wanted = f"{canon} {num}" if num else canon
    for c in candidates:
        if c.lower() == wanted.lower():
            return c
    if num is None:
        # "V" when the song has "Verse 1" only -> Verse 1
        numbered = [c for c in candidates if c.lower().startswith(canon.lower() + " ")]
        if len(numbered) == 1:
            return numbered[0]
    if num == "1":
        for c in candidates:
            if c.lower() == canon.lower():
                return c
    raise ArrangementError(f"arrangement refers to {wanted!r}, but the song has: {', '.join(candidates)}")


def parse_arrangement(text: str, song: Song, *, name: str = "Sunday", source: str = "leader") -> Arrangement:
    parts = [p.strip() for p in re.split(r"[,\n>;|]+|\s+-\s+|→", text) if p.strip()]
    tokens: list[str] = []
    rep_word = re.compile(r"(?:x|\*)\d+|\d+x", re.I)
    for p in parts:
        # allow space separated short forms: "V1 C V2 C B x2"
        words = p.split()
        if len(words) > 1 and all(
            ABBREVIATIONS.get(w.lower().rstrip("0123456789")) or rep_word.fullmatch(w) for w in words
        ):
            tokens.extend(words)
        else:
            tokens.append(p)
    steps: list[RepeatInstruction] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # "C x2" written with a space
        if i + 1 < len(tokens) and re.fullmatch(r"(?:x|\*)\s*\d+|\d+x", tokens[i + 1], re.I):
            tok = tok + " " + tokens[i + 1]
            i += 1
        m = _TOKEN.match(tok)
        if not m:
            raise ArrangementError(f"cannot read arrangement step {tok!r}")
        nm = m.group("name")
        num = m.group("num")
        # "Verse1" style: digits glued to the name are captured by num already
        rep = m.group("rep") or m.group("rep2") or m.group("rep3")
        section = _resolve(nm, num, song)
        steps.append(RepeatInstruction(section=section, times=int(rep) if rep else 1, partial=m.group("note")))
        i += 1
    if not steps:
        raise ArrangementError("arrangement is empty")
    return Arrangement(name=name, steps=steps, source=source)  # type: ignore[arg-type]


def format_arrangement(arr: Arrangement) -> str:
    out = []
    for s in arr.steps:
        out.append(s.section + (f" x{s.times}" if s.times > 1 else "") + (f" [{s.partial}]" if s.partial else ""))
    return ", ".join(out)
