"""End-to-end song preparation: find -> parse -> arrange -> segment -> write -> QA -> approve -> publish."""
from __future__ import annotations

import difflib
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .arrangement import format_arrangement, parse_arrangement
from .lyrics.parser import parse_lyrics
from .lyrics.segment import SegmentOptions, segment_song
from .models import ReadinessState, SongPlan, ThemeReference
from .native.reader import read_pro, slide_sequence
from .native.theme import resolve_style
from .native.writer import write_pro
from .qa import run_checks

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Config:
    library_dirs: list[str] = field(default_factory=lambda: [os.path.join(PKG_ROOT, "songs")])
    output_dir: str = os.path.join(PKG_ROOT, "out")
    test_import_dir: str = os.path.join(PKG_ROOT, "out", "test-import")
    publish_dirs: list[str] = field(default_factory=list)  # where approved songs may be copied
    production_paths: list[str] = field(default_factory=list)  # never written to directly
    default_theme: str = "standard"
    propresenter_host: str = os.environ.get("PROPRESENTER_HOST", "127.0.0.1")
    propresenter_port: int = int(os.environ.get("PROPRESENTER_PORT", "50001"))
    allow_ui_automation: bool = False
    audit_log: str = os.path.join(PKG_ROOT, "out", "audit.log")

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        path = path or os.environ.get("WORSHIPFLOW_CONFIG") or os.path.join(PKG_ROOT, "worshipflow.config.json")
        cfg = cls()
        if os.path.exists(path):
            with open(path) as fh:
                data = json.load(fh)
            base = os.path.dirname(os.path.abspath(path))
            for k, v in data.items():
                if k.startswith("_") or not hasattr(cfg, k):
                    continue
                if isinstance(v, str) and k.endswith(("_dir", "_log")):
                    v = os.path.join(base, os.path.expanduser(v))
                if isinstance(v, list) and k.endswith(("_dirs", "_paths")):
                    v = [os.path.join(base, os.path.expanduser(x)) for x in v]
                setattr(cfg, k, v)
        return cfg


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "song"


def find_songs(query: str, cfg: Config) -> list[dict[str, Any]]:
    """Search the church's authorized lyric library (plain-text lyric sheets)."""
    results = []
    q = query.lower().strip()
    for d in cfg.library_dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.txt"), recursive=True)):
            try:
                with open(path, encoding="utf-8") as fh:
                    head = fh.read(2000)
            except OSError:
                continue
            meta = dict(re.findall(r"^(title|artist|version|source|authorized):\s*(.+)$", head, re.M))
            title = meta.get("title", os.path.basename(path))
            hay = f"{title} {meta.get('artist', '')}".lower()
            score = difflib.SequenceMatcher(None, q, title.lower()).ratio()
            if q in hay:
                score = max(score, 0.9)
            if all(w in hay for w in q.split()):
                score = max(score, 0.8)
            if score >= 0.55:
                results.append({"path": path, "title": title, "artist": meta.get("artist", ""),
                                "version": meta.get("version", ""), "authorized": meta.get("authorized", "false"),
                                "score": round(score, 2)})
    return sorted(results, key=lambda r: -r["score"])


def build_plan(lyrics_text: str, *, arrangement: Optional[str] = None, theme: Optional[str] = None,
               lines_per_slide: int = 2, version: Optional[str] = None) -> tuple[SongPlan, Any]:
    song = parse_lyrics(lyrics_text)
    if version:
        song.version.label = version
    if arrangement:
        song.arrangement = parse_arrangement(arrangement, song, source="leader")
    style = resolve_style(theme)
    opt = SegmentOptions(max_lines_per_slide=lines_per_slide, max_line_chars=style.max_line_chars)
    plan = segment_song(song, opt, ThemeReference(name=style.name, source=style.source, path=style.path))  # type: ignore[arg-type]
    return plan, style


def file_hash(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def prepare(lyrics_path: str, cfg: Config, *, arrangement: Optional[str] = None, theme: Optional[str] = None,
            lines_per_slide: int = 2, version: Optional[str] = None, out_dir: Optional[str] = None,
            uuid_seed: Optional[str] = None) -> dict[str, Any]:
    with open(lyrics_path, encoding="utf-8") as fh:
        text = fh.read()
    plan, style = build_plan(text, arrangement=arrangement, theme=theme or cfg.default_theme,
                             lines_per_slide=lines_per_slide, version=version)
    out_dir = out_dir or cfg.output_dir
    for p in cfg.production_paths:
        if os.path.realpath(out_dir).startswith(os.path.realpath(p)):
            raise PermissionError(f"refusing to write drafts into production path {p}")
    os.makedirs(out_dir, exist_ok=True)
    slug = slugify(plan.song.title)
    pro_path = os.path.join(out_dir, f"{slug}.pro")
    write_pro(plan, pro_path, style, uuid_seed=uuid_seed)
    desc = read_pro(pro_path)
    report = run_checks(plan, desc, output_path=pro_path, production_paths=cfg.production_paths,
                        style_font=style.font_info)
    plan.approval.state = report.state
    with open(os.path.join(out_dir, f"{slug}.plan.json"), "w") as fh:
        fh.write(plan.model_dump_json(indent=2))
    with open(os.path.join(out_dir, f"{slug}.qa.json"), "w") as fh:
        fh.write(report.model_dump_json(indent=2))
    with open(os.path.join(out_dir, f"{slug}.preview.txt"), "w") as fh:
        fh.write(render_preview(plan, desc))
    return {
        "title": plan.song.title, "pro_path": pro_path, "state": report.state.value,
        "slides": len(plan.cues), "arrangement": format_arrangement(plan.song.arrangement),
        "theme": style.name, "sha256": file_hash(pro_path),
        "checks": {c.id: c.status for c in report.checks},
        "uncertainties": report.uncertainties,
    }


def regenerate(pro_path: str, cfg: Config, *, arrangement: Optional[str] = None, theme: Optional[str] = None,
               uuid_seed: Optional[str] = None) -> dict[str, Any]:
    """Rebuild a draft with a new arrangement and/or theme. Lyrics and slide breaks stay as planned."""
    base = pro_path[: -len(".pro")]
    plan = load_plan(base + ".plan.json")
    if plan.approval.state in (ReadinessState.APPROVED, ReadinessState.PUBLISHED):
        plan.approval.state = ReadinessState.DRAFT  # any change voids the approval
        plan.approval.note = "approval cleared: song was changed"
    if arrangement:
        plan.song.arrangement = parse_arrangement(arrangement, plan.song, source="leader")
    style = resolve_style(theme or plan.theme.path or None)
    plan.theme = ThemeReference(name=style.name, source=style.source, path=style.path)  # type: ignore[arg-type]
    write_pro(plan, pro_path, style, uuid_seed=uuid_seed)
    desc = read_pro(pro_path)
    report = run_checks(plan, desc, output_path=pro_path, production_paths=cfg.production_paths, style_font=style.font_info)
    plan.approval.state = report.state
    with open(base + ".plan.json", "w") as fh:
        fh.write(plan.model_dump_json(indent=2))
    with open(base + ".qa.json", "w") as fh:
        fh.write(report.model_dump_json(indent=2))
    with open(base + ".preview.txt", "w") as fh:
        fh.write(render_preview(plan, desc))
    return {"pro_path": pro_path, "state": report.state.value, "arrangement": format_arrangement(plan.song.arrangement),
            "theme": style.name, "sha256": file_hash(pro_path), "checks": {c.id: c.status for c in report.checks}}


def render_preview(plan: SongPlan, desc: Optional[dict] = None) -> str:
    out = [f"{plan.song.title}  ({plan.song.version.label})", f"Theme: {plan.theme.name}",
           f"Arrangement: {format_arrangement(plan.song.arrangement)}", ""]
    seq = slide_sequence(desc) if desc else [(n, c.text) for n in plan.song.arrangement.expanded() for c in plan.cues_for(n)]
    last = None
    for i, (group, text) in enumerate(seq, 1):
        if group != last:
            out.append(f"== {group} ==")
            last = group
        body = text.replace("\n", "\n      ") if text else "(blank / instrumental)"
        out.append(f"{i:>3}.  {body}")
    return "\n".join(out) + "\n"


def load_plan(path: str) -> SongPlan:
    with open(path) as fh:
        return SongPlan.model_validate_json(fh.read())


def _audit(cfg: Config, event: str, **data: Any) -> None:
    os.makedirs(os.path.dirname(cfg.audit_log), exist_ok=True)
    with open(cfg.audit_log, "a") as fh:
        fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": event, **data}) + "\n")


def approve(pro_path: str, cfg: Config, *, approved_by: str, note: str = "") -> dict[str, Any]:
    """Record a human approval bound to the exact file bytes."""
    if not approved_by.strip():
        raise ValueError("approved_by (a person's name) is required")
    base = pro_path[: -len(".pro")]
    with open(base + ".qa.json") as fh:
        qa = json.load(fh)
    blocking = [c for c in qa["checks"] if c["status"] == "fail" and c["critical"]]
    if blocking:
        raise PermissionError(f"cannot approve: critical checks failed: {[c['id'] for c in blocking]}")
    plan = load_plan(base + ".plan.json")
    plan.approval.state = ReadinessState.APPROVED
    plan.approval.approved_by = approved_by
    plan.approval.approved_at = datetime.now(timezone.utc).isoformat()
    plan.approval.note = f"{note} sha256={file_hash(pro_path)}".strip()
    with open(base + ".plan.json", "w") as fh:
        fh.write(plan.model_dump_json(indent=2))
    _audit(cfg, "approve", file=pro_path, by=approved_by, sha256=file_hash(pro_path))
    return {"state": "APPROVED", "approved_by": approved_by, "sha256": file_hash(pro_path)}


def publish(pro_path: str, dest_dir: str, cfg: Config, *, allow_overwrite: bool = False) -> dict[str, Any]:
    """Copy an APPROVED song into an allowed folder (e.g. the import inbox). Never overwrites by default."""
    base = pro_path[: -len(".pro")]
    plan = load_plan(base + ".plan.json")
    if plan.approval.state != ReadinessState.APPROVED:
        raise PermissionError("song is not approved - run `worshipflow approve` first")
    if f"sha256={file_hash(pro_path)}" not in plan.approval.note:
        raise PermissionError("file changed after approval - re-run QA and approve again")
    real = os.path.realpath(dest_dir)
    if not any(real == os.path.realpath(d) or real.startswith(os.path.realpath(d) + os.sep) for d in cfg.publish_dirs):
        raise PermissionError(f"{dest_dir} is not in publish_dirs in the config")
    safe_title = re.sub(r'[/\\:*?"<>|]+', "-", plan.song.title).strip() or "Song"
    target = os.path.join(dest_dir, f"{safe_title}.pro")
    if os.path.exists(target) and not allow_overwrite:
        raise FileExistsError(f"{target} already exists - refusing to overwrite without explicit permission")
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(pro_path, target)
    plan.approval.state = ReadinessState.PUBLISHED
    with open(base + ".plan.json", "w") as fh:
        fh.write(plan.model_dump_json(indent=2))
    _audit(cfg, "publish", file=pro_path, to=target, by=plan.approval.approved_by, sha256=file_hash(target))
    return {"state": "PUBLISHED", "path": target}


def stage_for_test_import(pro_path: str, cfg: Config, *, open_in_propresenter: bool = False) -> dict[str, Any]:
    """Copy a draft into the test-import folder; optionally ask macOS to open it in ProPresenter.

    Opening is EXPERIMENTAL: what ProPresenter 22 does with an opened .pro (import
    dialog vs. direct add to the active library) has not been verified yet.
    """
    os.makedirs(cfg.test_import_dir, exist_ok=True)
    target = os.path.join(cfg.test_import_dir, os.path.basename(pro_path))
    shutil.copy2(pro_path, target)
    result: dict[str, Any] = {"staged": target, "opened": False}
    if open_in_propresenter:
        if not cfg.allow_ui_automation:
            result["note"] = "allow_ui_automation is false in the config; import manually with File > Import"
        elif platform.system() != "Darwin":
            result["note"] = "not on macOS; copy the file to the church Mac and import it there"
        else:
            subprocess.run(["open", "-a", "ProPresenter", target], check=True)
            result["opened"] = True
    _audit(cfg, "stage_test_import", file=target, opened=result["opened"])
    return result
