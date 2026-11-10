"""Parse a lyric sheet into a structured :class:`Song`.

Accepted input (plain text, UTF-8):

    ---
    title: Morning Light
    artist: The Way Worship
    version: Live
    source: original            # church_library | user_supplied | ccli_songselect | public_domain | original | test_fixture
    authorized: true
    ccli: 1234567               # optional
    arrangement: V1, C, V2, C, B x2, C
    ---
    [Verse 1]
    first line
    second line

    third line                  # a blank line forces a new slide
    [Chorus]
    ...

Section headers may be written ``[Verse 1]``, ``Verse 1:``, ``VERSE 1`` or
``(Chorus)``. A header that repeats an earlier section with no lyrics under it
(or the identical lyrics) is treated as a *repeat* in the performance order,
which is how most printed lyric sheets show a returning chorus.

Bilingual lines: ``English line || Linea en espanol`` or a parallel section
named with a language suffix, e.g. ``[Verse 1 (ES)]``.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import (
    Arrangement,
    LyricSource,
    RepeatInstruction,
    Song,
    SongSection,
    SongVersion,
    SectionKind,
)

KIND_WORDS: list[tuple[re.Pattern[str], SectionKind, str]] = [
    (re.compile(r"^pre[\s-]?chorus$", re.I), SectionKind.PRE_CHORUS, "Pre-Chorus"),
    (re.compile(r"^post[\s-]?chorus$", re.I), SectionKind.POST_CHORUS, "Post-Chorus"),
    (re.compile(r"^(verse|verso|estrofa)$", re.I), SectionKind.VERSE, "Verse"),
    (re.compile(r"^(chorus|coro)$", re.I), SectionKind.CHORUS, "Chorus"),
    (re.compile(r"^(bridge|puente)$", re.I), SectionKind.BRIDGE, "Bridge"),
    (re.compile(r"^(intro|introduction)$", re.I), SectionKind.INTRO, "Intro"),
    (re.compile(r"^(outro)$", re.I), SectionKind.OUTRO, "Outro"),
    (re.compile(r"^(ending|end|final)$", re.I), SectionKind.ENDING, "Ending"),
    (re.compile(r"^(tag)$", re.I), SectionKind.TAG, "Tag"),
    (re.compile(r"^(vamp)$", re.I), SectionKind.VAMP, "Vamp"),
    (re.compile(r"^(refrain)$", re.I), SectionKind.REFRAIN, "Refrain"),
    (re.compile(r"^(interlude|turnaround)$", re.I), SectionKind.INTERLUDE, "Interlude"),
    (re.compile(r"^(instrumental|inst|solo|music)$", re.I), SectionKind.INSTRUMENTAL, "Instrumental"),
    (re.compile(r"^(blank)$", re.I), SectionKind.BLANK, "Blank"),
]

INSTRUMENTAL_KINDS = {SectionKind.INTRO, SectionKind.INSTRUMENTAL, SectionKind.INTERLUDE, SectionKind.OUTRO, SectionKind.BLANK}

_HEADER_RE = re.compile(
    r"""^\s*
    (?:\[(?P<b>[^\]]+)\]            # [Verse 1]
      |\((?P<p>[^)]+)\)              # (Chorus)
      |(?P<c>[A-Za-z][A-Za-z \-]*?\s*\d*)\s*:   # Verse 1:
      |(?P<u>[A-Z][A-Z \-]*?\s*\d*)  # VERSE 1 (all caps, whole line)
    )\s*(?P<rep>(?:x\s*\d+|\d+\s*x|\*\s*\d+))?\s*$""",
    re.X,
)
_LANG_SUFFIX = re.compile(r"^(?P<base>.+?)\s*(?:\((?P<l1>[A-Za-z]{2})\)|-\s*(?P<l2>[A-Za-z]{2}))$")
_REPEAT_TAIL = re.compile(r"\s*(?:\(\s*(?:x\s*\d+|\d+\s*x|repeat)\s*\)|\bx\s*\d+|\b\d+x)\s*$", re.I)


class LyricParseError(ValueError):
    pass


def classify_header(label: str) -> Optional[tuple[str, SectionKind, Optional[int]]]:
    """Return (canonical name, kind, number) if ``label`` looks like a section header."""
    label = re.sub(r"\s+", " ", label.strip())
    m = re.match(r"^(?P<word>[A-Za-z][A-Za-z \-]*?)\s*(?P<num>\d+)?$", label)
    if not m:
        return None
    word = m.group("word").strip()
    num = int(m.group("num")) if m.group("num") else None
    for pat, kind, canon in KIND_WORDS:
        if pat.match(word):
            name = f"{canon} {num}" if num is not None else canon
            return name, kind, num
    return None


def _parse_header_line(line: str) -> Optional[tuple[str, SectionKind, Optional[int], Optional[str], int]]:
    """Return (name, kind, number, language, repeat_times) for a header line."""
    m = _HEADER_RE.match(line)
    if not m:
        return None
    raw = m.group("b") or m.group("p") or m.group("c") or m.group("u")
    if raw is None:
        return None
    if m.group("u") is not None and line.strip() != line.strip().upper():
        return None
    lang = None
    lm = _LANG_SUFFIX.match(raw.strip())
    if lm and classify_header(lm.group("base")):
        lang = (lm.group("l1") or lm.group("l2")).lower()
        raw = lm.group("base")
    info = classify_header(raw)
    if info is None:
        return None
    rep = 1
    if m.group("rep"):
        rep = int(re.sub(r"\D", "", m.group("rep")))
    name, kind, num = info
    return name, kind, num, lang, rep


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return meta, "\n".join(lines[i + 1 :])
        if ":" in lines[i]:
            k, v = lines[i].split(":", 1)
            meta[k.strip().lower()] = v.strip()
    raise LyricParseError("front matter starts with '---' but is never closed")


def strip_repeat_marker(line: str) -> tuple[str, Optional[str]]:
    """Remove a trailing performance marker like ``(x2)`` for display."""
    m = _REPEAT_TAIL.search(line)
    if not m or m.start() == 0:
        return line, None
    return line[: m.start()].rstrip(), m.group(0).strip()


def parse_lyrics(text: str, *, default_source: Optional[LyricSource] = None) -> Song:
    meta, body = _parse_front_matter(text.replace("\r\n", "\n").replace("\r", "\n"))
    title = meta.get("title", "").strip()
    if not title:
        raise LyricParseError("song title is required (front matter 'title:')")

    if "source" in meta:
        source = LyricSource(
            kind=meta["source"],  # validated by pydantic
            reference=meta.get("source_ref", ""),
            authorized=meta.get("authorized", "false").lower() in {"true", "yes", "1"},
            license_note=meta.get("license", ""),
        )
    elif default_source is not None:
        source = default_source
    else:
        source = LyricSource(kind="user_supplied", authorized=False)

    sections: list[SongSection] = []
    order: list[RepeatInstruction] = []
    translations: dict[str, list[str]] = {}
    current: Optional[SongSection] = None
    current_lang: Optional[str] = None
    current_is_repeat_candidate = False
    pending_blank = False
    preamble: list[str] = []

    def by_name(name: str) -> Optional[SongSection]:
        for s in sections:
            if s.name.lower() == name.lower():
                return s
        return None

    def close_current() -> None:
        nonlocal current, current_is_repeat_candidate
        if current is None:
            return
        if current_is_repeat_candidate:
            original = by_name(current.name)
            assert original is not None
            if current.source_lines and current.source_lines != original.source_lines:
                # Same header, different words: keep both, number the new one.
                n = 2
                while by_name(f"{current.name} {n}"):
                    n += 1
                current.name = f"{current.name} {n}"
                sections.append(current)
                order.append(RepeatInstruction(section=current.name))
            else:
                order.append(RepeatInstruction(section=original.name))
        current = None
        current_is_repeat_candidate = False

    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        header = _parse_header_line(line) if line.strip() else None
        if header:
            if current_lang is None:
                close_current()
            name, kind, num, lang, rep = header
            pending_blank = False
            if lang:
                current_lang = lang
                translations[name] = []
                current = None
                continue
            current_lang = None
            if by_name(name) is not None:
                current = SongSection(name=name, kind=kind, number=num)
                current_is_repeat_candidate = True
                for _ in range(rep - 1):
                    order.append(RepeatInstruction(section=name))
                continue
            current = SongSection(name=name, kind=kind, number=num, instrumental=kind in INSTRUMENTAL_KINDS)
            sections.append(current)
            order.append(RepeatInstruction(section=name, times=rep))
            continue
        if not line.strip():
            pending_blank = True
            continue
        if current_lang is not None:
            # parallel translation section
            target = list(translations.keys())[-1]
            translations[target].append(line.strip())
            continue
        if current is None:
            preamble.append(line)
            continue
        text_line = line.strip()
        tr: Optional[str] = None
        if "||" in text_line:
            a, b = text_line.split("||", 1)
            text_line, tr = a.strip(), b.strip()
        if pending_blank and current.source_lines:
            current.explicit_breaks.append(len(current.source_lines))
        pending_blank = False
        current.source_lines.append(text_line)
        current.translation_lines.append(tr)
        current.instrumental = False if current.kind not in {SectionKind.BLANK} else True
    close_current()

    if preamble and not sections:
        # No headers at all: treat as one section.
        sec = SongSection(name="Verse 1", kind=SectionKind.VERSE, number=1)
        for i, ln in enumerate(preamble):
            sec.source_lines.append(ln.strip())
            sec.translation_lines.append(None)
        sections.append(sec)
        order.append(RepeatInstruction(section="Verse 1"))
    elif preamble:
        raise LyricParseError(f"lyrics found before the first section header: {preamble[0]!r}")

    for name, lines in translations.items():
        sec = by_name(name)
        if sec is None:
            raise LyricParseError(f"translation given for unknown section {name!r}")
        if len(lines) != len(sec.source_lines):
            raise LyricParseError(
                f"translation for {name!r} has {len(lines)} lines but the section has {len(sec.source_lines)}"
            )
        sec.translation_lines = list(lines)

    # Empty non-instrumental sections are almost always a mistake.
    for s in sections:
        if not s.source_lines and s.kind not in INSTRUMENTAL_KINDS:
            raise LyricParseError(f"section {s.name!r} has no lyrics")
        if not s.source_lines:
            s.instrumental = True

    song = Song(
        title=title,
        artist=meta.get("artist", ""),
        authors=meta.get("authors", meta.get("author", "")),
        ccli_number=int(meta["ccli"]) if meta.get("ccli", "").isdigit() else None,
        copyright_year=int(meta["year"]) if meta.get("year", "").isdigit() else None,
        publisher=meta.get("publisher", ""),
        language=meta.get("language", "en"),
        version=SongVersion(label=meta.get("version", "default"), reference_url=meta.get("reference", "")),
        source=source,
        sections=sections,
        arrangement=Arrangement(name=meta.get("arrangement_name", "Sunday"), steps=order, source="lyric_file"),
    )
    if meta.get("arrangement"):
        from ..arrangement import parse_arrangement

        song.arrangement = parse_arrangement(meta["arrangement"], song, source="leader")
    return song
