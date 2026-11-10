"""Typed song model for WorshipFlow.

Rule of the road: the exact authorized lyric text (``SongSection.source_lines``)
is never rewritten. Slide cues only *group* those lines; any display change
(e.g. dropping a trailing comma) is recorded separately so QA can prove the
words on screen match the authorized source.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReadinessState(str, enum.Enum):
    DRAFT = "DRAFT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    READY_FOR_IMPORT = "READY_FOR_IMPORT"
    IMPORTED = "IMPORTED"
    VERIFIED = "VERIFIED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


class SectionKind(str, enum.Enum):
    INTRO = "intro"
    VERSE = "verse"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    POST_CHORUS = "post_chorus"
    BRIDGE = "bridge"
    INTERLUDE = "interlude"
    INSTRUMENTAL = "instrumental"
    TAG = "tag"
    VAMP = "vamp"
    REFRAIN = "refrain"
    ENDING = "ending"
    OUTRO = "outro"
    BLANK = "blank"
    OTHER = "other"


class LyricSource(BaseModel):
    """Where the words came from. Every song must carry one."""

    kind: Literal["church_library", "user_supplied", "ccli_songselect", "public_domain", "original", "test_fixture"]
    reference: str = ""  # file path, SongSelect id, URL, or note
    authorized: bool = False
    license_note: str = ""


class SongVersion(BaseModel):
    label: str = "default"  # e.g. "Live", "Radio", "Spanish"
    reference_url: str = ""  # e.g. a YouTube URL used only as a reference
    notes: str = ""


class MusicalPhrase(BaseModel):
    """One singable line of lyrics (exact source text)."""

    text: str
    translation: Optional[str] = None  # bilingual partner line, if any
    source_line_index: int  # index into the section's source_lines


class SongSection(BaseModel):
    name: str  # display/group name, e.g. "Verse 1"
    kind: SectionKind = SectionKind.OTHER
    number: Optional[int] = None
    source_lines: list[str] = Field(default_factory=list)  # exact authorized text
    translation_lines: list[Optional[str]] = Field(default_factory=list)
    explicit_breaks: list[int] = Field(default_factory=list)  # line indexes that start a new slide (blank line in source)
    phrases: list[MusicalPhrase] = Field(default_factory=list)
    instrumental: bool = False


class SlideCue(BaseModel):
    section: str
    index_in_section: int
    lines: list[str]
    translation_lines: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # e.g. "three_lines", "four_lines_review"

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class RepeatInstruction(BaseModel):
    section: str
    times: int = 1
    partial: Optional[str] = None  # free-text note, e.g. "last two lines"


class Arrangement(BaseModel):
    name: str = "Sunday"
    steps: list[RepeatInstruction] = Field(default_factory=list)
    source: Literal["leader", "lyric_file", "detected", "default"] = "default"

    def expanded(self) -> list[str]:
        out: list[str] = []
        for s in self.steps:
            out.extend([s.section] * max(1, s.times))
        return out


class PerformanceReference(BaseModel):
    kind: Literal["youtube", "audio_file", "rehearsal_notes", "lyric_sheet", "other"]
    reference: str
    notes: str = ""
    authorized: bool = False


class ThemeReference(BaseModel):
    name: str = "WorshipFlow Default"
    source: Literal["builtin", "theme_folder", "template_song"] = "builtin"
    path: str = ""
    slide_name: str = ""  # layout name inside a ProPresenter theme


class Song(BaseModel):
    title: str
    artist: str = ""
    authors: str = ""
    ccli_number: Optional[int] = None
    copyright_year: Optional[int] = None
    publisher: str = ""
    language: str = "en"
    version: SongVersion = Field(default_factory=SongVersion)
    source: LyricSource
    sections: list[SongSection] = Field(default_factory=list)
    arrangement: Arrangement = Field(default_factory=Arrangement)
    references: list[PerformanceReference] = Field(default_factory=list)

    def section(self, name: str) -> Optional[SongSection]:
        key = name.strip().lower()
        for s in self.sections:
            if s.name.lower() == key:
                return s
        return None


class QualityCheck(BaseModel):
    id: str
    name: str
    status: Literal["pass", "fail", "warn", "not_run"]
    critical: bool = True
    detail: str = ""


class QualityReport(BaseModel):
    song_title: str
    state: ReadinessState
    checks: list[QualityCheck] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def critical_failures(self) -> list[QualityCheck]:
        return [c for c in self.checks if c.critical and c.status == "fail"]


class ApprovalStatus(BaseModel):
    state: ReadinessState = ReadinessState.DRAFT
    approved_by: str = ""
    approved_at: str = ""
    note: str = ""


class SongPlan(BaseModel):
    """Everything needed to write a native presentation."""

    song: Song
    cues: list[SlideCue]
    theme: ThemeReference = Field(default_factory=ThemeReference)
    approval: ApprovalStatus = Field(default_factory=ApprovalStatus)

    def cues_for(self, section: str) -> list[SlideCue]:
        return [c for c in self.cues if c.section == section]
