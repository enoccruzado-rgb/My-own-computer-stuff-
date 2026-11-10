"""worshipflow command line.

    worshipflow doctor                      check this machine + ProPresenter connection
    worshipflow find "morning light"        search the authorized lyric library
    worshipflow analyze song.txt            show sections, arrangement and planned slides
    worshipflow prepare song.txt            write <out>/<song>.pro + plan, QA report, preview
    worshipflow preview out/song.pro        print slides in performance order
    worshipflow inspect file.pro            dump any .pro file (groups, slides, arrangements)
    worshipflow import out/song.pro         stage a draft for a TEST library import
    worshipflow verify out/song.pro [--live]  re-run QA (with --live: check inside ProPresenter)
    worshipflow approve out/song.pro --by "Name"
    worshipflow publish out/song.pro --to <publish dir>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys

from . import __version__
from .arrangement import format_arrangement
from .native.reader import read_pro
from .native.theme import BUILTIN_PRESETS, list_theme_slides, resolve_style
from .propresenter_api import ProPresenterClient, ProPresenterError, verify_live
from .qa import run_checks
from .workflow import (Config, approve, build_plan, find_songs, load_plan, prepare, publish, render_preview,
                       stage_for_test_import)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_doctor(a, cfg: Config) -> int:
    import google.protobuf

    report = {
        "worshipflow": __version__,
        "python": sys.version.split()[0],
        "protobuf": google.protobuf.__version__,
        "os": f"{platform.system()} {platform.release()}",
        "library_dirs": {d: os.path.isdir(d) for d in cfg.library_dirs},
        "output_dir": cfg.output_dir,
        "publish_dirs": cfg.publish_dirs,
        "builtin_themes": list(BUILTIN_PRESETS),
        "ui_automation": cfg.allow_ui_automation,
    }
    client = ProPresenterClient(cfg.propresenter_host, cfg.propresenter_port)
    try:
        report["propresenter"] = client.version()
        report["propresenter_libraries"] = [l["id"]["name"] for l in client.libraries()]
    except ProPresenterError as e:
        report["propresenter"] = f"not reachable: {e}"
    _print(report)
    return 0


def cmd_find(a, cfg):
    _print(find_songs(a.query, cfg))
    return 0


def cmd_analyze(a, cfg):
    plan, style = build_plan(open(a.lyrics, encoding="utf-8").read(), arrangement=a.arrangement,
                             theme=a.theme or cfg.default_theme, lines_per_slide=a.lines)
    out = {
        "title": plan.song.title, "version": plan.song.version.label, "source": plan.song.source.model_dump(),
        "sections": [{"name": s.name, "kind": s.kind.value, "lines": len(s.source_lines),
                      "slides": len(plan.cues_for(s.name))} for s in plan.song.sections],
        "arrangement": format_arrangement(plan.song.arrangement),
        "theme": style.name,
        "flags": sorted({f for c in plan.cues for f in c.flags}),
    }
    _print(out)
    print()
    print(render_preview(plan))
    return 0


def cmd_prepare(a, cfg):
    res = prepare(a.lyrics, cfg, arrangement=a.arrangement, theme=a.theme, lines_per_slide=a.lines,
                  version=a.version, out_dir=a.out)
    _print(res)
    return 0 if res["state"] in ("READY_FOR_IMPORT", "VERIFIED", "NEEDS_REVIEW") else 1


def cmd_preview(a, cfg):
    base = a.pro[: -len(".pro")]
    if os.path.exists(base + ".plan.json"):
        print(render_preview(load_plan(base + ".plan.json"), read_pro(a.pro)))
    else:
        from .native.reader import slide_sequence

        for g, t in slide_sequence(read_pro(a.pro)):
            print(f"[{g}] {t}")
    return 0


def cmd_inspect(a, cfg):
    _print(read_pro(a.pro))
    return 0


def cmd_import(a, cfg):
    _print(stage_for_test_import(a.pro, cfg, open_in_propresenter=a.open))
    return 0


def cmd_verify(a, cfg):
    base = a.pro[: -len(".pro")]
    plan = load_plan(base + ".plan.json")
    style = resolve_style(plan.theme.path or None)
    evidence = None
    if a.live:
        client = ProPresenterClient(cfg.propresenter_host, cfg.propresenter_port)
        evidence = verify_live(plan, client, presentation_uuid=a.uuid, thumbnails_dir=base + ".thumbs")
    report = run_checks(plan, read_pro(a.pro), output_path=a.pro, production_paths=cfg.production_paths,
                        style_font=style.font_info, propresenter_evidence=evidence)
    with open(base + ".qa.json", "w") as fh:
        fh.write(report.model_dump_json(indent=2))
    _print({"state": report.state.value, "checks": [c.model_dump() for c in report.checks],
            "uncertainties": report.uncertainties})
    return 0 if not report.critical_failures else 1


def cmd_approve(a, cfg):
    _print(approve(a.pro, cfg, approved_by=a.by, note=a.note or ""))
    return 0


def cmd_publish(a, cfg):
    _print(publish(a.pro, a.to, cfg, allow_overwrite=a.allow_overwrite))
    return 0


def cmd_themes(a, cfg):
    out = {"builtin": list(BUILTIN_PRESETS)}
    if a.folder:
        out["theme_slides"] = list_theme_slides(a.folder)
    try:
        out["propresenter"] = ProPresenterClient(cfg.propresenter_host, cfg.propresenter_port).themes()
    except ProPresenterError as e:
        out["propresenter"] = f"not reachable: {e}"
    _print(out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="worshipflow", description="Build native ProPresenter song presentations.")
    p.add_argument("--config", help="path to worshipflow.config.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("find"); s.add_argument("query"); s.set_defaults(fn=cmd_find)
    for name, fn in (("analyze", cmd_analyze), ("prepare", cmd_prepare)):
        s = sub.add_parser(name)
        s.add_argument("lyrics")
        s.add_argument("--arrangement", help='e.g. "V1, C, V2, C, B x2, C, Tag"')
        s.add_argument("--theme", help="builtin preset, path to a template .pro, or theme folder[::slide name]")
        s.add_argument("--lines", type=int, default=2, help="max lines per slide (default 2)")
        s.add_argument("--version", help="version label, e.g. Live")
        s.add_argument("--out", help="output folder")
        s.set_defaults(fn=fn)
    s = sub.add_parser("preview"); s.add_argument("pro"); s.set_defaults(fn=cmd_preview)
    s = sub.add_parser("inspect"); s.add_argument("pro"); s.set_defaults(fn=cmd_inspect)
    s = sub.add_parser("import"); s.add_argument("pro"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_import)
    s = sub.add_parser("verify"); s.add_argument("pro"); s.add_argument("--live", action="store_true"); s.add_argument("--uuid"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("approve"); s.add_argument("pro"); s.add_argument("--by", required=True); s.add_argument("--note"); s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("publish"); s.add_argument("pro"); s.add_argument("--to", required=True); s.add_argument("--allow-overwrite", action="store_true"); s.set_defaults(fn=cmd_publish)
    s = sub.add_parser("themes"); s.add_argument("--folder"); s.set_defaults(fn=cmd_themes)
    a = p.parse_args(argv)
    cfg = Config.load(a.config)
    try:
        return a.fn(a, cfg)
    except (ValueError, PermissionError, FileExistsError, FileNotFoundError, ProPresenterError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
