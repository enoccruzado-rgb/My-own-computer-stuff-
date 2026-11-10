import json
import os
import tempfile
import unittest

from worshipflow.native import rtf
from worshipflow.native.reader import read_pro
from worshipflow.native.theme import (builtin_style, list_theme_slides, resolve_style, style_from_template_song,
                                      style_from_theme_folder)
from worshipflow.native.writer import build_presentation, write_pro
from worshipflow.qa import run_checks
from worshipflow.workflow import Config, approve, build_plan, prepare, publish

HERE = os.path.dirname(__file__)
NATIVE = os.path.join(HERE, "fixtures", "native")
DEMO = os.path.join(HERE, "..", "songs", "demo", "morning-light.txt")


def _demo():
    with open(DEMO, encoding="utf-8") as fh:
        return fh.read()


class RtfTests(unittest.TestCase):
    def test_roundtrip_unicode(self):
        for text in ["Amazing grace", "Café — “quotes” ’n ñ", "Line one\nLine two", "Emoji 😀 ok", r"back\slash {braces}"]:
            self.assertEqual(rtf.rtf_to_text(rtf.build_rtf(text)), text)

    def test_retext_keeps_formatting(self):
        src = rtf.build_rtf("old words", font="OpenSans-Bold", size_pt=60)
        new = rtf.retext_rtf(src, "new words\nsecond")
        self.assertEqual(rtf.rtf_to_text(new), "new words\nsecond")
        self.assertEqual(rtf.rtf_font_info(new)["font"], "OpenSans-Bold")
        self.assertEqual(rtf.rtf_font_info(new)["size_pt"], 60)

    def test_reads_real_propresenter_file(self):
        d = read_pro(os.path.join(NATIVE, "reference-Test.pro"))
        self.assertEqual(d["name"], "Test")
        self.assertEqual([g["name"] for g in d["groups"]], ["Verse 1", "Verse 2", "Chorus", "Ending"])
        self.assertEqual(d["groups"][0]["slides"][0]["texts"][0], "Vers1.1\nVers1.2")
        self.assertEqual(d["arrangements"][0]["groups"], ["Chorus", "Verse 1", "Chorus", "Verse 2", "Chorus"])


class ThemeTests(unittest.TestCase):
    def _check(self, style):
        plan, _ = build_plan(_demo())
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.pro")
            write_pro(plan, p, style)
            desc = read_pro(p)
            rep = run_checks(plan, desc, style_font=style.font_info)
        self.assertEqual([c.id for c in rep.checks if c.status == "fail"], [])
        return desc

    def test_real_theme_folder(self):
        folder = os.path.join(NATIVE, "sample-theme")
        self.assertIn("Liedtext", list_theme_slides(folder))
        style = style_from_theme_folder(folder, "Liedtext")
        self.assertEqual(style.font_info["font"], "OpenSans-Bold")
        desc = self._check(style)
        els = desc["groups"][0]["slides"][0]["elements"]
        self.assertEqual(els[0]["font"], "OpenSans-Bold")
        self.assertEqual(len(els), 2)  # lyric box + the theme's background layer
        self.assertEqual(resolve_style(folder + "::Liedtext").font_info["font"], "OpenSans-Bold")

    def test_template_song(self):
        style = style_from_template_song(os.path.join(NATIVE, "reference-Test.pro"))
        desc = self._check(style)
        self.assertEqual(desc["groups"][0]["slides"][0]["elements"][0]["bounds"], [150.0, 100.0, 1620.0, 880.0])

    def test_all_builtin_presets(self):
        for name in ("standard", "cinematic", "youth", "bilingual"):
            self._check(builtin_style(name))

    def test_deterministic_output(self):
        plan, style = build_plan(_demo())
        a = build_presentation(plan, style, uuid_seed="x").SerializeToString()
        b = build_presentation(plan, style, uuid_seed="x").SerializeToString()
        self.assertEqual(a, b)
        uuids = [c.uuid.string for c in build_presentation(plan, style).cues]
        self.assertEqual(len(uuids), len(set(uuids)))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = Config(output_dir=os.path.join(self.tmp, "out"), publish_dirs=[os.path.join(self.tmp, "inbox")],
                          production_paths=[os.path.join(self.tmp, "prod")], audit_log=os.path.join(self.tmp, "audit.log"))

    def test_prepare_approve_publish(self):
        res = prepare(DEMO, self.cfg)
        self.assertEqual(res["state"], "READY_FOR_IMPORT")
        self.assertEqual(res["slides"], 8)
        with self.assertRaises(PermissionError):
            publish(res["pro_path"], os.path.join(self.tmp, "inbox"), self.cfg)  # not approved yet
        with self.assertRaises(ValueError):
            approve(res["pro_path"], self.cfg, approved_by=" ")
        approve(res["pro_path"], self.cfg, approved_by="Test Leader")
        with self.assertRaises(PermissionError):
            publish(res["pro_path"], os.path.join(self.tmp, "elsewhere"), self.cfg)  # not an allowed folder
        out = publish(res["pro_path"], os.path.join(self.tmp, "inbox"), self.cfg)
        self.assertTrue(os.path.exists(out["path"]))
        with open(self.cfg.audit_log) as fh:
            log = [json.loads(l) for l in fh]
        self.assertEqual([e["event"] for e in log], ["approve", "publish"])

    def test_publish_refuses_overwrite_and_tampering(self):
        res = prepare(DEMO, self.cfg)
        approve(res["pro_path"], self.cfg, approved_by="Leader")
        publish(res["pro_path"], os.path.join(self.tmp, "inbox"), self.cfg)
        # re-approve after publish so state is APPROVED again, then try to overwrite
        approve(res["pro_path"], self.cfg, approved_by="Leader")
        with self.assertRaises(FileExistsError):
            publish(res["pro_path"], os.path.join(self.tmp, "inbox"), self.cfg)
        with open(res["pro_path"], "ab") as fh:
            fh.write(b"\x00")
        with self.assertRaises(PermissionError):
            publish(res["pro_path"], os.path.join(self.tmp, "inbox"), self.cfg, allow_overwrite=True)

    def test_refuses_to_write_drafts_into_production(self):
        with self.assertRaises(PermissionError):
            prepare(DEMO, self.cfg, out_dir=os.path.join(self.tmp, "prod", "lib"))

    def test_unapprovable_when_critical_fail(self):
        p = os.path.join(HERE, "fixtures", "lyrics", "19-unauthorized.txt")
        res = prepare(p, self.cfg)
        self.assertEqual(res["state"], "DRAFT")
        with self.assertRaises(PermissionError):
            approve(res["pro_path"], self.cfg, approved_by="Leader")


if __name__ == "__main__":
    unittest.main()
