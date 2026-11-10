"""Read any ProPresenter .pro file back into plain data for verification."""
from __future__ import annotations

from typing import Any

from . import rtf as rtfmod
from .rvproto import presentation_pb2


def load_presentation(path: str) -> presentation_pb2.Presentation:
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        raise ValueError(f"{path} is empty (0 bytes) - not a valid ProPresenter file")
    pres = presentation_pb2.Presentation()
    pres.ParseFromString(data)
    return pres


def describe(pres: presentation_pb2.Presentation) -> dict[str, Any]:
    cues = {c.uuid.string: c for c in pres.cues}
    groups = []
    group_names = {}
    for cg in pres.cue_groups:
        group_names[cg.group.uuid.string] = cg.group.name
        slides = []
        for ident in cg.cue_identifiers:
            cue = cues.get(ident.string)
            if cue is None:
                slides.append({"uuid": ident.string, "missing": True})
                continue
            texts, elements = [], []
            for action in cue.actions:
                if not (action.HasField("slide") and action.slide.HasField("presentation")):
                    continue
                for se in action.slide.presentation.base_slide.elements:
                    el = se.element
                    info: dict[str, Any] = {
                        "name": el.name,
                        "bounds": [el.bounds.origin.x, el.bounds.origin.y, el.bounds.size.width, el.bounds.size.height],
                    }
                    if el.HasField("text") and el.text.rtf_data:
                        txt = rtfmod.rtf_to_text(el.text.rtf_data)
                        info.update({"text": txt, **rtfmod.rtf_font_info(el.text.rtf_data),
                                     "attr_font": el.text.attributes.font.name or None})
                        if txt.strip():
                            texts.append(txt)
                    elements.append(info)
            slides.append({"uuid": ident.string, "enabled": cue.isEnabled, "texts": texts, "elements": elements})
        groups.append({"name": cg.group.name, "uuid": cg.group.uuid.string, "slides": slides})
    arrangements = []
    for a in pres.arrangements:
        arrangements.append({
            "name": a.name, "uuid": a.uuid.string,
            "groups": [group_names.get(g.string, f"<missing {g.string}>") for g in a.group_identifiers],
        })
    selected = next((a["name"] for a in arrangements if a["uuid"] == pres.selected_arrangement.string), None)
    referenced = {i.string for cg in pres.cue_groups for i in cg.cue_identifiers}
    return {
        "name": pres.name,
        "uuid": pres.uuid.string,
        "app_version": f"{pres.application_info.application_version.major_version}.{pres.application_info.application_version.minor_version}",
        "groups": groups,
        "arrangements": arrangements,
        "selected_arrangement": selected,
        "orphan_cues": [u for u in cues if u not in referenced],
        "ccli": {"song_number": pres.ccli.song_number, "author": pres.ccli.author, "title": pres.ccli.song_title},
    }


def read_pro(path: str) -> dict[str, Any]:
    return describe(load_presentation(path))


def slide_sequence(desc: dict[str, Any], arrangement: str | None = None) -> list[tuple[str, str]]:
    """Slides in performance order: [(group name, text)]."""
    arr = None
    for a in desc["arrangements"]:
        if (arrangement and a["name"] == arrangement) or (not arrangement and a["name"] == desc["selected_arrangement"]):
            arr = a
    order = arr["groups"] if arr else [g["name"] for g in desc["groups"]]
    by_name = {g["name"]: g for g in desc["groups"]}
    seq = []
    for name in order:
        for s in by_name.get(name, {"slides": []})["slides"]:
            texts = s.get("texts", [])
            seq.append((name, texts[0] if texts else ""))
    return seq
