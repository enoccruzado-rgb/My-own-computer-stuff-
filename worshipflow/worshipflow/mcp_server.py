"""WorshipFlow MCP server (stdio).

Only tools that are actually implemented are exposed. Nothing here can trigger
slides, clear screens or change looks: there is no code path to the LED wall.
Approval is deliberately NOT a tool - a person runs `worshipflow approve`.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Optional

from .arrangement import format_arrangement, parse_arrangement
from .lyrics.parser import parse_lyrics
from .native.reader import read_pro, slide_sequence
from .native.theme import BUILTIN_PRESETS, PRESET_TITLES, list_theme_slides
from .propresenter_api import ProPresenterClient, ProPresenterError, verify_live
from .qa import run_checks
from .workflow import (Config, build_plan, find_songs, load_plan, prepare, publish, regenerate, render_preview,
                       stage_for_test_import)
from .native.theme import resolve_style

CFG = Config.load()


def _client() -> ProPresenterClient:
    return ProPresenterClient(CFG.propresenter_host, CFG.propresenter_port)


def _err(e: Exception) -> dict[str, Any]:
    return {"ok": False, "error": type(e).__name__, "detail": str(e)}


def _text(lyrics_path: str = "", lyrics_text: str = "") -> str:
    if lyrics_text:
        return lyrics_text
    if not lyrics_path:
        raise ValueError("give lyrics_path (a file in the authorized library) or lyrics_text")
    with open(lyrics_path, encoding="utf-8") as fh:
        return fh.read()


# ---------------- discovery ----------------
def propresenter_connect() -> dict:
    """Check the connection to ProPresenter's local API (read-only). Returns version and library names."""
    try:
        c = _client()
        return {"ok": True, "version": c.version(), "libraries": [l["id"]["name"] for l in c.libraries()],
                "base_url": c.base}
    except ProPresenterError as e:
        return _err(e)


def propresenter_get_version() -> dict:
    """ProPresenter machine name, platform and host description (GET /version)."""
    try:
        return {"ok": True, **_client().version()}
    except ProPresenterError as e:
        return _err(e)


def propresenter_list_libraries(include_items: bool = False) -> dict:
    """List ProPresenter libraries, optionally with the presentations in each."""
    try:
        c = _client()
        libs = c.libraries()
        if include_items:
            for l in libs:
                l["items"] = c.library(l["id"]["uuid"]).get("items", [])
        return {"ok": True, "libraries": libs}
    except ProPresenterError as e:
        return _err(e)


def propresenter_list_themes(theme_folder: str = "") -> dict:
    """Themes available: WorshipFlow presets, layouts in a ProPresenter theme folder, and (if reachable) ProPresenter's own themes."""
    out: dict[str, Any] = {"ok": True, "builtin_presets": {k: PRESET_TITLES[k] for k in BUILTIN_PRESETS}}
    if theme_folder:
        try:
            out["theme_folder_slides"] = list_theme_slides(theme_folder)
        except (OSError, ValueError) as e:
            out["theme_folder_error"] = str(e)
    try:
        out["propresenter_themes"] = _client().themes()
    except ProPresenterError as e:
        out["propresenter_themes"] = f"not reachable: {e}"
    return out


def propresenter_get_presentation(uuid: str = "", pro_path: str = "") -> dict:
    """Read a presentation: from ProPresenter by UUID, or straight from a .pro file path."""
    try:
        if pro_path:
            return {"ok": True, "source": "file", **read_pro(pro_path)}
        return {"ok": True, "source": "api", "presentation": _client().presentation(uuid)}
    except (ProPresenterError, OSError, ValueError) as e:
        return _err(e)


def propresenter_get_thumbnails(uuid: str, out_dir: str, count: int = 0) -> dict:
    """Save PNG thumbnails of a presentation's slides (rendered by ProPresenter) into out_dir."""
    try:
        c = _client()
        n = count or sum(len(g.get("slides", [])) for g in c.presentation(uuid).get("groups", []))
        os.makedirs(out_dir, exist_ok=True)
        files = []
        for i in range(n):
            p = os.path.join(out_dir, f"slide-{i + 1:02d}.png")
            with open(p, "wb") as fh:
                fh.write(c.thumbnail(uuid, i))
            files.append(p)
        return {"ok": True, "files": files}
    except (ProPresenterError, OSError) as e:
        return _err(e)


# ---------------- song intelligence ----------------
def song_find(query: str) -> dict:
    """Search the church's authorized lyric library. Multiple hits (duplicate titles/versions) are all returned."""
    hits = find_songs(query, CFG)
    return {"ok": True, "count": len(hits), "results": hits,
            "note": "" if hits else "Not in the library. Ask the worship leader for approved lyrics; never type lyrics from memory."}


def song_load_authorized_lyrics(lyrics_path: str) -> dict:
    """Load a lyric sheet and report whether it is marked authorized."""
    try:
        song = parse_lyrics(_text(lyrics_path))
        return {"ok": True, "title": song.title, "artist": song.artist, "version": song.version.label,
                "source": song.source.model_dump(), "authorized": song.source.authorized, "text": _text(lyrics_path)}
    except (OSError, ValueError) as e:
        return _err(e)


def song_parse_sections(lyrics_path: str = "", lyrics_text: str = "") -> dict:
    """Parse a lyric sheet into sections (verse/chorus/bridge...) with exact source lines."""
    try:
        song = parse_lyrics(_text(lyrics_path, lyrics_text))
        return {"ok": True, "title": song.title,
                "sections": [{"name": s.name, "kind": s.kind.value, "lines": s.source_lines,
                              "translation": [t for t in s.translation_lines if t]} for s in song.sections],
                "arrangement_from_sheet": format_arrangement(song.arrangement)}
    except (OSError, ValueError) as e:
        return _err(e)


def song_analyze_arrangement(arrangement: str, lyrics_path: str = "", lyrics_text: str = "") -> dict:
    """Check a leader's arrangement (e.g. 'V1 C V2 C B x2 C Tag') against the song's sections."""
    try:
        song = parse_lyrics(_text(lyrics_path, lyrics_text))
        arr = parse_arrangement(arrangement, song)
        unused = [s.name for s in song.sections if s.name not in arr.expanded()]
        return {"ok": True, "arrangement": format_arrangement(arr), "order": arr.expanded(),
                "sections_not_used": unused, "partials": [s.model_dump() for s in arr.steps if s.partial]}
    except (OSError, ValueError) as e:
        return _err(e)


def song_generate_cues(lyrics_path: str = "", lyrics_text: str = "", arrangement: str = "", theme: str = "",
                       lines_per_slide: int = 2) -> dict:
    """Plan slides (dry run, writes nothing): natural 1-2 line phrases per slide, with review flags."""
    try:
        plan, style = build_plan(_text(lyrics_path, lyrics_text), arrangement=arrangement or None,
                                 theme=theme or CFG.default_theme, lines_per_slide=lines_per_slide)
        return {"ok": True, "theme": style.name, "preview": render_preview(plan),
                "cues": [c.model_dump() for c in plan.cues]}
    except (OSError, ValueError) as e:
        return _err(e)


def song_validate(pro_path: str) -> dict:
    """Re-run file-level QA on a prepared .pro (needs its .plan.json next to it)."""
    try:
        plan = load_plan(pro_path[:-4] + ".plan.json")
        style = resolve_style(plan.theme.path or None)
        rep = run_checks(plan, read_pro(pro_path), output_path=pro_path, production_paths=CFG.production_paths,
                         style_font=style.font_info)
        return {"ok": True, **rep.model_dump(mode="json")}
    except (OSError, ValueError) as e:
        return _err(e)


# ---------------- native authoring ----------------
def propresenter_create_song(lyrics_path: str = "", lyrics_text: str = "", arrangement: str = "", theme: str = "",
                             lines_per_slide: int = 2, version: str = "", dry_run: bool = True) -> dict:
    """Create a native ProPresenter .pro song (groups, slides, arrangement, theme) in the drafts folder.

    dry_run=True (default) only returns the planned slides. The file is written to the
    WorshipFlow drafts folder, never into a live ProPresenter library.
    """
    try:
        if dry_run:
            return {"dry_run": True, **song_generate_cues(lyrics_path, lyrics_text, arrangement, theme, lines_per_slide)}
        path = lyrics_path
        if lyrics_text and not lyrics_path:
            os.makedirs(CFG.output_dir, exist_ok=True)
            path = os.path.join(CFG.output_dir, "_input.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(lyrics_text)
        return {"ok": True, **prepare(path, CFG, arrangement=arrangement or None, theme=theme or None,
                                      lines_per_slide=lines_per_slide, version=version or None)}
    except (OSError, ValueError, PermissionError) as e:
        return _err(e)


def propresenter_set_arrangement(pro_path: str, arrangement: str) -> dict:
    """Change the arrangement of a draft (e.g. 'V1, C, V2, C, B x2, C'). Clears any approval."""
    try:
        return {"ok": True, **regenerate(pro_path, CFG, arrangement=arrangement)}
    except (OSError, ValueError) as e:
        return _err(e)


def propresenter_apply_theme(pro_path: str, theme: str) -> dict:
    """Restyle a draft: builtin preset name, path to a template .pro, or 'theme folder::slide name'. Clears any approval."""
    try:
        return {"ok": True, **regenerate(pro_path, CFG, theme=theme)}
    except (OSError, ValueError) as e:
        return _err(e)


def propresenter_import_to_test_library(pro_path: str, open_in_propresenter: bool = False) -> dict:
    """Stage a draft in the test-import folder. Opening in ProPresenter is experimental and off unless enabled in config."""
    try:
        return {"ok": True, **stage_for_test_import(pro_path, CFG, open_in_propresenter=open_in_propresenter)}
    except (OSError, ValueError) as e:
        return _err(e)


def propresenter_verify_song(pro_path: str, live: bool = False, presentation_uuid: str = "") -> dict:
    """Verify a song. live=True also checks it inside ProPresenter (text, saved file, thumbnails)."""
    try:
        plan = load_plan(pro_path[:-4] + ".plan.json")
        style = resolve_style(plan.theme.path or None)
        ev = verify_live(plan, _client(), presentation_uuid=presentation_uuid or None,
                         thumbnails_dir=pro_path[:-4] + ".thumbs") if live else None
        rep = run_checks(plan, read_pro(pro_path), output_path=pro_path, production_paths=CFG.production_paths,
                         style_font=style.font_info, propresenter_evidence=ev)
        return {"ok": True, "evidence": ev, **rep.model_dump(mode="json")}
    except (OSError, ValueError, ProPresenterError) as e:
        return _err(e)


# ---------------- review ----------------
def song_preview(pro_path: str) -> dict:
    """Text preview of the slides in performance order."""
    try:
        plan = load_plan(pro_path[:-4] + ".plan.json")
        return {"ok": True, "preview": render_preview(plan, read_pro(pro_path))}
    except (OSError, ValueError) as e:
        return _err(e)


def song_quality_report(pro_path: str) -> dict:
    """The saved machine-readable QA report for a draft."""
    try:
        with open(pro_path[:-4] + ".qa.json") as fh:
            import json

            return {"ok": True, **json.load(fh)}
    except (OSError, ValueError) as e:
        return _err(e)


def song_compare(pro_a: str, pro_b: str) -> dict:
    """Compare two .pro files slide by slide (e.g. last week's version vs. the new draft)."""
    try:
        a, b = slide_sequence(read_pro(pro_a)), slide_sequence(read_pro(pro_b))
        diffs = [{"slide": i + 1, "a": x, "b": y} for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return {"ok": True, "same": a == b, "slides_a": len(a), "slides_b": len(b), "differences": diffs[:50]}
    except (OSError, ValueError) as e:
        return _err(e)


def song_request_approval(pro_path: str) -> dict:
    """Summarize a draft for a human reviewer and tell them how to approve. Does NOT approve."""
    try:
        plan = load_plan(pro_path[:-4] + ".plan.json")
        rep = song_quality_report(pro_path)
        return {"ok": True, "title": plan.song.title, "state": plan.approval.state.value,
                "preview": render_preview(plan, read_pro(pro_path)),
                "open_items": rep.get("uncertainties", []),
                "how_to_approve": f'A worship leader runs: worshipflow approve "{pro_path}" --by "Their Name"'}
    except (OSError, ValueError) as e:
        return _err(e)


def song_publish(pro_path: str, dest_dir: str, allow_overwrite: bool = False) -> dict:
    """Copy an APPROVED, unchanged draft into an allowed publish folder (audit logged). Refuses overwrites by default."""
    try:
        return {"ok": True, **publish(pro_path, dest_dir, CFG, allow_overwrite=allow_overwrite)}
    except (OSError, ValueError, PermissionError) as e:
        return _err(e)


TOOLS = [
    propresenter_connect, propresenter_get_version, propresenter_list_libraries, propresenter_list_themes,
    propresenter_get_presentation, propresenter_get_thumbnails,
    song_find, song_load_authorized_lyrics, song_parse_sections, song_analyze_arrangement, song_generate_cues,
    song_validate,
    propresenter_create_song, propresenter_set_arrangement, propresenter_apply_theme,
    propresenter_import_to_test_library, propresenter_verify_song,
    song_preview, song_quality_report, song_compare, song_request_approval, song_publish,
]


def serve() -> None:
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("worshipflow")
    for fn in TOOLS:
        server.tool()(fn)
    server.run()


if __name__ == "__main__":
    serve()
