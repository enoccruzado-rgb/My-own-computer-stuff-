"""Slide styling sources.

Three ways to style generated slides, best first:

1. ``template_song`` - a song the church already formatted in ProPresenter and
   exported (.pro). We clone its first lyric slide's text box (font, size,
   position, shadow, stroke, RTF formatting) and any non-text layers. This is
   the most faithful option because ProPresenter itself wrote the styling.
2. ``theme_folder`` - a ProPresenter theme folder (contains a ``Theme`` file,
   an ``rv.data.Template.Document``). We clone the chosen theme slide layout.
3. ``builtin`` - WorshipFlow's own presets, built from scratch.

ProPresenter's API cannot apply a theme to a presentation (confirmed against
openapi.propresenter.com), so styling is carried inside the native file.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from typing import Optional

from .rvproto import graphicsData_pb2 as gfx
from .rvproto import presentation_pb2, slide_pb2, template_pb2
from . import rtf as rtfmod


@dataclass
class SlideStyle:
    name: str
    text_element: slide_pb2.Slide.Element  # prototype lyric text box (with text)
    translation_element: Optional[slide_pb2.Slide.Element] = None
    decorations: list[slide_pb2.Slide.Element] = field(default_factory=list)  # non-lyric layers kept as-is
    slide_size: tuple[float, float] = (1920.0, 1080.0)
    uppercase: bool = False
    source: str = "builtin"
    path: str = ""
    max_line_chars: int = 38

    @property
    def font_info(self) -> dict:
        return rtfmod.rtf_font_info(self.text_element.element.text.rtf_data)


def _color(msg, r, g, b, a=1.0):
    msg.red, msg.green, msg.blue, msg.alpha = r, g, b, a


def _rect_path(path: gfx.Graphics.Path) -> None:
    path.closed = True
    for x, y in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)):
        p = path.points.add()
        for pt in (p.point, p.q0, p.q1):
            pt.x, pt.y = x, y
    path.shape.type = gfx.Graphics.Path.Shape.TYPE_RECTANGLE


def make_text_element(
    name: str,
    bounds: tuple[float, float, float, float],
    *,
    font: str,
    family: str,
    size_pt: float,
    color=(255, 255, 255),
    align: str = "center",
    shadow: bool = True,
    bold: bool = False,
) -> slide_pb2.Slide.Element:
    se = slide_pb2.Slide.Element()
    el = se.element
    el.uuid.string = "00000000-0000-0000-0000-000000000000"  # replaced per slide
    el.name = name
    x, y, w, h = bounds
    el.bounds.origin.x, el.bounds.origin.y = x, y
    el.bounds.size.width, el.bounds.size.height = w, h
    el.opacity = 1.0
    _rect_path(el.path)
    _color(el.fill.color, 0.13, 0.59, 0.95)
    el.stroke.width = 3.0
    _color(el.stroke.color, 1, 1, 1)
    el.shadow.angle, el.shadow.offset, el.shadow.radius, el.shadow.opacity = 315.0, 5.0, 5.0, 0.75
    _color(el.shadow.color, 0, 0, 0)
    el.feather.radius = 0.05
    t = el.text
    t.attributes.font.name = font
    t.attributes.font.size = size_pt
    t.attributes.font.family = family
    t.attributes.font.bold = bold
    _color(t.attributes.text_solid_fill, color[0] / 255, color[1] / 255, color[2] / 255)
    t.attributes.paragraph_style.alignment = {
        "left": gfx.Graphics.Text.Attributes.ALIGNMENT_LEFT,
        "right": gfx.Graphics.Text.Attributes.ALIGNMENT_RIGHT,
        "center": gfx.Graphics.Text.Attributes.ALIGNMENT_CENTER,
    }[align]
    t.attributes.paragraph_style.line_height_multiple = 1.0
    t.attributes.paragraph_style.default_tab_interval = 84.0
    if shadow:
        t.shadow.enable = True
    t.shadow.angle, t.shadow.offset, t.shadow.radius, t.shadow.opacity = 315.0, 3.0, 6.0, 0.8
    _color(t.shadow.color, 0, 0, 0)
    t.rtf_data = rtfmod.build_rtf("", font=font, size_pt=size_pt, color=color, align=align, bold=bold)
    t.vertical_alignment = gfx.Graphics.Text.VERTICAL_ALIGNMENT_MIDDLE
    t.is_superscript_standardized = True
    t.transformDelimiter = "  •  "
    se.info = 3
    se.text_scroller.scroll_rate = 0.5
    se.text_scroller.should_repeat = True
    se.text_scroller.repeat_distance = 0.06172839506172839
    return se


# Built-in presets. Font: Helvetica Neue ships with every Mac running ProPresenter.
BUILTIN_PRESETS = {
    "standard": dict(bounds=(120, 240, 1680, 600), size=72, align="center", upper=False, max_chars=38),
    "cinematic": dict(bounds=(160, 700, 1600, 300), size=60, align="center", upper=False, max_chars=44),
    "youth": dict(bounds=(120, 240, 1680, 600), size=78, align="center", upper=True, max_chars=30, bold=True),
    "bilingual": dict(bounds=(120, 170, 1680, 400), size=64, align="center", upper=False, max_chars=40,
                      tr_bounds=(120, 600, 1680, 330), tr_size=52),
}
PRESET_TITLES = {
    "standard": "Standard Worship",
    "cinematic": "Cinematic Worship",
    "youth": "Youth Night",
    "bilingual": "Bilingual Worship",
}


def builtin_style(preset: str = "standard") -> SlideStyle:
    key = preset.lower().split()[0]
    if key not in BUILTIN_PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose one of {', '.join(BUILTIN_PRESETS)}")
    p = BUILTIN_PRESETS[key]
    bold = p.get("bold", False)
    font = "HelveticaNeue-Bold" if bold else "HelveticaNeue"
    text = make_text_element("Lyrics", p["bounds"], font=font, family="Helvetica Neue", size_pt=p["size"],
                             align=p["align"], bold=bold)
    tr = None
    if "tr_bounds" in p:
        tr = make_text_element("Translation", p["tr_bounds"], font="HelveticaNeue-Italic", family="Helvetica Neue",
                               size_pt=p["tr_size"], color=(255, 214, 120), align=p["align"])
    return SlideStyle(name=PRESET_TITLES[key], text_element=text, translation_element=tr, uppercase=p["upper"],
                      source="builtin", path=key, max_line_chars=p["max_chars"])


def _split_layers(elements, prefer_name: str = "") -> tuple[slide_pb2.Slide.Element, Optional[slide_pb2.Slide.Element], list]:
    texts = [e for e in elements if e.element.HasField("text") and e.element.text.rtf_data]
    plain = [e for e in texts if rtfmod.rtf_to_text(e.element.text.rtf_data).strip() or True]
    if not plain:
        raise ValueError("template slide has no text box to clone")

    def area(e):
        return e.element.bounds.size.width * e.element.bounds.size.height

    # A full-screen box that carries no words is a background, not the lyric box.
    candidates = [e for e in plain if rtfmod.rtf_to_text(e.element.text.rtf_data).strip()] or plain
    named = [e for e in candidates if prefer_name and e.element.name.lower() == prefer_name.lower()]
    main = named[0] if named else max(candidates, key=area)
    others = [e for e in candidates if e is not main]
    translation = others[0] if len(candidates) >= 2 and len(others) == 1 else None
    deco = [e for e in elements if e is not main and e is not translation]
    return main, translation, deco


def style_from_template_song(path: str) -> SlideStyle:
    pres = presentation_pb2.Presentation()
    with open(path, "rb") as fh:
        pres.ParseFromString(fh.read())
    for cue in pres.cues:
        for action in cue.actions:
            if action.HasField("slide") and action.slide.HasField("presentation"):
                bs = action.slide.presentation.base_slide
                if any(e.element.HasField("text") and rtfmod.rtf_to_text(e.element.text.rtf_data).strip() for e in bs.elements):
                    main, tr, deco = _split_layers(bs.elements)
                    return SlideStyle(
                        name=f"Template: {pres.name}", text_element=copy.deepcopy(main),
                        translation_element=copy.deepcopy(tr) if tr else None,
                        decorations=[copy.deepcopy(d) for d in deco],
                        slide_size=(bs.size.width or 1920.0, bs.size.height or 1080.0),
                        source="template_song", path=path,
                    )
    raise ValueError(f"{path}: no slide with text found to use as a template")


def load_theme_document(path: str) -> template_pb2.Template.Document:
    theme_file = os.path.join(path, "Theme") if os.path.isdir(path) else path
    doc = template_pb2.Template.Document()
    with open(theme_file, "rb") as fh:
        doc.ParseFromString(fh.read())
    return doc


def list_theme_slides(path: str) -> list[str]:
    return [s.name for s in load_theme_document(path).slides]


def style_from_theme_folder(path: str, slide_name: str = "") -> SlideStyle:
    doc = load_theme_document(path)
    if not doc.slides:
        raise ValueError(f"{path}: theme has no slides")
    chosen = None
    if slide_name:
        for s in doc.slides:
            if s.name.lower() == slide_name.lower():
                chosen = s
        if chosen is None:
            raise ValueError(f"theme slide {slide_name!r} not found; available: {[s.name for s in doc.slides]}")
    else:
        for s in doc.slides:
            if any(k in s.name.lower() for k in ("lyric", "song", "worship", "liedtext", "letra")):
                chosen = s
                break
        chosen = chosen or doc.slides[0]
    main, tr, deco = _split_layers(chosen.base_slide.elements)
    bs = chosen.base_slide
    return SlideStyle(
        name=f"Theme: {os.path.basename(path.rstrip('/'))} / {chosen.name}",
        text_element=copy.deepcopy(main), translation_element=copy.deepcopy(tr) if tr else None,
        decorations=[copy.deepcopy(d) for d in deco],
        slide_size=(bs.size.width or 1920.0, bs.size.height or 1080.0),
        source="theme_folder", path=path,
    )


def resolve_style(theme: Optional[str]) -> SlideStyle:
    """``theme`` may be a preset name, a .pro template path, or a theme folder."""
    if not theme:
        return builtin_style("standard")
    if os.path.isdir(theme) or os.path.basename(theme) == "Theme":
        name = ""
        return style_from_theme_folder(theme, name)
    if "::" in theme:
        folder, name = theme.split("::", 1)
        return style_from_theme_folder(folder, name)
    if theme.lower().endswith(".pro") and os.path.exists(theme):
        return style_from_template_song(theme)
    return builtin_style(theme)
