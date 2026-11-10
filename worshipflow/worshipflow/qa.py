"""Quality checks: compare the plan with what was actually written/imported.

Every check says pass / fail / warn / not_run. "not_run" is used honestly for
anything that needs ProPresenter itself (import, thumbnails, reopen) when no
evidence was supplied - those never silently pass.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from .lyrics.parser import strip_repeat_marker
from .models import QualityCheck, QualityReport, ReadinessState, SongPlan
from .native.reader import slide_sequence

AVG_CHAR_WIDTH = 0.53  # of font size, for a typical sans face
LINE_HEIGHT = 1.2


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def estimate_fit(text: str, size_pt: float, box_w: float, box_h: float) -> dict[str, Any]:
    lines = text.split("\n") if text else []
    rendered = 0
    widest = 0.0
    for ln in lines:
        w = len(ln) * size_pt * AVG_CHAR_WIDTH
        widest = max(widest, w)
        rendered += max(1, int(w // max(box_w, 1)) + (1 if w % max(box_w, 1) else 0)) if w > box_w else 1
    height = rendered * size_pt * LINE_HEIGHT
    return {"rendered_lines": rendered, "widest_px": round(widest), "height_px": round(height),
            "fits_width": widest <= box_w, "fits_height": height <= box_h}


def run_checks(
    plan: SongPlan,
    desc: dict[str, Any],
    *,
    output_path: str = "",
    production_paths: Optional[list[str]] = None,
    expected_title: Optional[str] = None,
    expected_version: Optional[str] = None,
    style_font: Optional[dict] = None,
    propresenter_evidence: Optional[dict[str, Any]] = None,
) -> QualityReport:
    song = plan.song
    checks: list[QualityCheck] = []
    unc: list[str] = []

    def add(id_, name, ok, detail="", critical=True, warn=False):
        status = "pass" if ok else ("warn" if warn else "fail")
        checks.append(QualityCheck(id=id_, name=name, status=status, critical=critical, detail=detail))

    # 0. Lyrics are authorized
    add("lyrics_authorized", "Lyrics come from an authorized source", song.source.authorized,
        f"source={song.source.kind} {song.source.reference}".strip())

    # 1. Correct song
    want = expected_title or song.title
    add("title", "Correct song title", _norm(desc["name"]).lower() == _norm(want).lower(),
        f"file={desc['name']!r} expected={want!r}")

    # 2. Version
    if expected_version:
        add("version", "Correct version", song.version.label.lower() == expected_version.lower(),
            f"plan={song.version.label!r} expected={expected_version!r}")
    else:
        checks.append(QualityCheck(id="version", name="Correct version", status="not_run", critical=False,
                                   detail=f"plan says {song.version.label!r}; no expected version given"))

    # 3. Lyrics exact: display words come from the source, in order, nothing added or dropped.
    lyric_problems = []
    for sec in song.sections:
        src_words = " ".join(_norm(strip_repeat_marker(l)[0]) for l in sec.source_lines)
        shown = " ".join(_norm(l) for c in plan.cues_for(sec.name) for l in c.lines)
        if src_words != shown:
            lyric_problems.append(f"{sec.name}: source and slides differ")
        group = next((g for g in desc["groups"] if g["name"] == sec.name), None)
        if group is not None:
            file_words = " ".join(_norm(t) for s in group["slides"] for t in s.get("texts", [])[:1])
            if _norm(file_words).casefold() != _norm(src_words).casefold():
                lyric_problems.append(f"{sec.name}: written file text differs from the source")
    add("lyrics_exact", "Lyrics match the authorized source exactly", not lyric_problems, "; ".join(lyric_problems))

    # 4. Grouping
    want_groups = [s.name for s in song.sections]
    got_groups = [g["name"] for g in desc["groups"]]
    add("groups", "Verse/chorus/bridge grouping", want_groups == got_groups, f"file groups={got_groups}")
    counts_ok = all(len(next(g for g in desc["groups"] if g["name"] == s.name)["slides"]) == len(plan.cues_for(s.name))
                    for s in song.sections if s.name in got_groups)
    add("group_slide_counts", "Each group holds the planned slides", counts_ok and not desc["orphan_cues"],
        f"orphan slides={len(desc['orphan_cues'])}")

    # 5/6. Arrangement and slide sequence
    want_arr = song.arrangement.expanded()
    got_arr = next((a["groups"] for a in desc["arrangements"] if a["name"] == desc["selected_arrangement"]), [])
    add("arrangement", "Correct repetitions / arrangement", want_arr == got_arr, f"file={got_arr}")
    expected_seq = [(name, c.text) for name in want_arr for c in plan.cues_for(name)]
    got_seq = slide_sequence(desc)
    seq_ok = len(expected_seq) == len(got_seq) and all(
        a[0] == b[0] and _norm(a[1]).casefold() == _norm(b[1]).casefold() for a, b in zip(expected_seq, got_seq)
    )
    add("sequence", "Correct slide sequence", seq_ok, f"{len(got_seq)} slides in performance order")

    # 7. Density
    four = [c for c in plan.cues if len(c.lines) >= 4]
    three = [c for c in plan.cues if len(c.lines) == 3]
    long_lines = [c for c in plan.cues if "line_too_long" in c.flags]
    add("density", "Lyric density (1-2 lines preferred)", not four and not long_lines,
        f"{len(three)} three-line, {len(four)} four-line, {len(long_lines)} with long lines", critical=False, warn=True)
    if three:
        unc.append(f"{len(three)} slide(s) use three lines - glance at them")
    for c in plan.cues:
        for f in c.flags:
            if f.startswith("repeat_marker_removed"):
                unc.append(f"{c.section}: a '{f.split(':', 1)[1]}' marker was removed from the screen text - confirm how many times the band repeats it")

    # 8/9. Theme + overflow
    lyric_elements = [e for g in desc["groups"] for s in g["slides"] for e in s.get("elements", []) if e.get("text")]
    primary = [next(e for e in s["elements"] if e.get("text")) for g in desc["groups"] for s in g["slides"]
               if any(e.get("text") for e in s.get("elements", []))]
    if style_font:
        bad = [e for e in primary if e.get("font") != style_font.get("font")
               or (style_font.get("size_pt") and e.get("size_pt") != style_font.get("size_pt"))]
        add("theme", "Theme styling applied to every lyric slide", not bad,
            f"expected font {style_font.get('font')} {style_font.get('size_pt')}pt; {len(bad)} slide(s) differ")
    else:
        checks.append(QualityCheck(id="theme", name="Theme styling applied", status="not_run", critical=False))
    overflow = []
    for e in lyric_elements:
        size = e.get("size_pt") or 42
        fit = estimate_fit(e["text"], size, e["bounds"][2], e["bounds"][3])
        if not (fit["fits_width"] and fit["fits_height"]):
            overflow.append(f"{e['text'][:30]!r} ~{fit['rendered_lines']} lines")
    add("overflow", "No text overflow (estimated)", not overflow, "; ".join(overflow[:5]), critical=False, warn=True)

    # 11. Editable text
    editable = all(s.get("texts") for g in desc["groups"] for s in g["slides"]
                   if not any(c.section == g["name"] and not c.lines for c in plan.cues))
    add("editable_text", "Lyrics are editable native text boxes", editable, "text stored as RTF text elements")

    # 10/12/13. Needs ProPresenter
    ev = propresenter_evidence or {}
    for id_, name in (("native_import", "Opened/imported in ProPresenter"),
                      ("thumbnails", "ProPresenter thumbnails rendered"),
                      ("persistence", "Same content after save and reopen")):
        if id_ in ev:
            add(id_, name, bool(ev[id_].get("ok")), ev[id_].get("detail", ""))
        else:
            checks.append(QualityCheck(id=id_, name=name, status="not_run", critical=True,
                                       detail="needs ProPresenter on the church Mac (run `worshipflow verify --live`)"))

    # 14. Production safety
    prod = [os.path.realpath(p) for p in (production_paths or [])]
    out = os.path.realpath(output_path) if output_path else ""
    unsafe = any(out.startswith(p + os.sep) or out == p for p in prod) if out else False
    add("production_safe", "No production content touched", not unsafe,
        f"output={output_path or '(memory)'}")

    hard_fail = [c for c in checks if c.status == "fail" and c.critical]
    needs_pp = [c for c in checks if c.status == "not_run" and c.critical]
    review = any("four_lines_review" in c.flags for c in plan.cues) or any(c.status == "warn" for c in checks)
    if hard_fail:
        state = ReadinessState.NEEDS_REVIEW if song.source.authorized else ReadinessState.DRAFT
    elif review:
        state = ReadinessState.NEEDS_REVIEW
    elif needs_pp:
        state = ReadinessState.READY_FOR_IMPORT
    else:
        state = ReadinessState.VERIFIED
    return QualityReport(song_title=song.title, state=state, checks=checks, uncertainties=list(dict.fromkeys(unc)))
