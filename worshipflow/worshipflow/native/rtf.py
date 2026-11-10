"""CocoaRTF helpers for ProPresenter slide text.

ProPresenter stores slide text as Apple CocoaRTF (``\\ansicpg1252``). Line
breaks inside one text box are RTF soft returns: a backslash followed by a
literal newline.
"""
from __future__ import annotations

import re

_CP1252_HIGH = {
    0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85, 0x2020: 0x86,
    0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A, 0x2039: 0x8B, 0x0152: 0x8C,
    0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92, 0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95,
    0x2013: 0x96, 0x2014: 0x97, 0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B,
    0x0153: 0x9C, 0x017E: 0x9E, 0x0178: 0x9F,
}
_CP1252_REV = {v: k for k, v in _CP1252_HIGH.items()}

ALIGN = {"left": r"\ql", "center": r"\qc", "right": r"\qr", "justify": r"\qj"}


def encode_text(text: str) -> str:
    out: list[str] = []
    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        cp = ord(ch)
        if ch == "\n":
            out.append("\\\n")
        elif ch in "\\{}":
            out.append("\\" + ch)
        elif 0x20 <= cp <= 0x7E:
            out.append(ch)
        elif cp < 0x20:
            continue
        elif 0xA0 <= cp <= 0xFF:
            out.append("\\'%02x" % cp)
        elif cp in _CP1252_HIGH:
            out.append("\\'%02x" % _CP1252_HIGH[cp])
        elif cp > 0xFFFF:
            v = cp - 0x10000
            for unit in (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)):
                out.append("\\u%d?" % (unit - 0x10000 if unit > 0x7FFF else unit))
        else:
            out.append("\\u%d?" % (cp - 0x10000 if cp > 0x7FFF else cp))
    return "".join(out)


def build_rtf(
    text: str,
    *,
    font: str = "HelveticaNeue",
    size_pt: float = 72,
    color: tuple[int, int, int] = (255, 255, 255),
    align: str = "center",
    bold: bool = False,
    uppercase: bool = False,
) -> bytes:
    body = encode_text(text.upper() if uppercase else text)
    r, g, b = color
    half_points = int(round(size_pt * 2))
    rtf = (
        "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2761\n"
        "\\cocoatextscaling0\\cocoaplatform0{\\fonttbl\\f0\\fnil\\fcharset0 " + font + ";}\n"
        "{\\colortbl;\\red255\\green255\\blue255;\\red%d\\green%d\\blue%d;}\n" % (r, g, b)
        + "{\\*\\expandedcolortbl;;\\cssrgb\\c%d\\c%d\\c%d;}\n" % (r * 100000 // 255, g * 100000 // 255, b * 100000 // 255)
        + "\\deftab1680\n"
        "\\pard\\pardeftab1680\\pardirnatural" + ALIGN.get(align, r"\qc") + "\\partightenfactor0\n\n"
        "\\f0" + ("\\b" if bold else "") + "\\fs%d \\cf2 \\CocoaLigature0 " % half_points + body + "}"
    )
    return rtf.encode("latin-1")


def _skip_group(s: str, i: int) -> int:
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def rtf_to_text(data: bytes | str) -> str:
    """Plain text from a CocoaRTF document (enough for verification)."""
    s = data.decode("latin-1") if isinstance(data, bytes) else data
    if not s.startswith("{\\rtf"):
        return s
    s = s[1:-1] if s.endswith("}") else s[1:]
    out: list[str] = []
    i = 0
    skip_fallback = 0
    while i < len(s):
        c = s[i]
        if c == "{":
            inner = s[i + 1 : i + 30]
            if inner.startswith(("\\fonttbl", "\\colortbl", "\\*", "\\stylesheet", "\\info")):
                i = _skip_group(s, i)
                continue
            i += 1
            continue
        if c == "}":
            i += 1
            continue
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt == "\n" or nxt == "\r":
                out.append("\n")
                i += 2
                continue
            if nxt in "\\{}":
                out.append(nxt)
                i += 2
                continue
            if nxt == "'":
                byte = int(s[i + 2 : i + 4], 16)
                out.append(chr(_CP1252_REV.get(byte, byte)))
                i += 4
                continue
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", s[i:])
            if m:
                word, arg = m.group(1), m.group(2)
                if word in ("par", "line"):
                    out.append("\n")
                elif word == "u" and arg is not None:
                    v = int(arg)
                    out.append(chr(v + 0x10000 if v < 0 else v))
                    skip_fallback = 1
                elif word == "tab":
                    out.append("\t")
                i += len(m.group(0))
                if skip_fallback and i < len(s) and s[i] == "?":
                    i += 1
                skip_fallback = 0
                continue
            i += 2
            continue
        if c in "\r\n":
            i += 1
            continue
        out.append(c)
        i += 1
    text = "".join(out)
    # Re-join UTF-16 surrogate pairs.
    try:
        text = text.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeDecodeError:
        pass
    return text.strip("\n")


def body_prefix(template_rtf: bytes) -> bytes:
    """Return the template RTF up to where its visible text begins.

    Used for theme/template cloning: we keep every formatting control word the
    church's own theme slide carries and swap only the words.
    """
    s = template_rtf.decode("latin-1")
    i = 1  # skip the opening brace
    last_ctrl_end = None
    while i < len(s):
        c = s[i]
        if c == "{":
            i = _skip_group(s, i)
            continue
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt in "\n\r\\{}'" :
                break  # escaped text character / soft return => text has begun
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", s[i:])
            if m:
                if m.group(1) == "u":
                    break
                i += len(m.group(0))
                last_ctrl_end = i
                continue
            i += 2
            continue
        if c in "\r\n":
            i += 1
            continue
        if c == "}":
            break
        break  # a literal character: the text starts here
    return s[:i].encode("latin-1")


def retext_rtf(template_rtf: bytes, text: str, *, uppercase: bool = False) -> bytes:
    prefix = body_prefix(template_rtf).decode("latin-1")
    if not prefix.endswith((" ", "\n")) and re.search(r"\\[a-zA-Z]+-?\d*$", prefix):
        prefix += " "
    return (prefix + encode_text(text.upper() if uppercase else text) + "}").encode("latin-1")


def rtf_font_info(data: bytes) -> dict:
    s = data.decode("latin-1")
    font = re.search(r"\\fonttbl\\f0\\f\w+\\fcharset\d+ ([^;]+);", s)
    size = re.findall(r"\\fs(\d+)", s)
    return {
        "font": font.group(1) if font else None,
        "size_pt": int(size[0]) / 2 if size else None,
        "align": next((k for k, v in ALIGN.items() if v + "\\" in s or s.count(v + " ")), None),
    }
