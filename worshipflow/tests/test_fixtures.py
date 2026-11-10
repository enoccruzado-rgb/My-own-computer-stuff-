"""Fixture tests: lyric sheet -> structure -> native .pro -> read back -> QA."""
import os
import tempfile
import unittest

from worshipflow.arrangement import ArrangementError, parse_arrangement
from worshipflow.lyrics.parser import LyricParseError, parse_lyrics
from worshipflow.lyrics.segment import SegmentOptions, segment_song
from worshipflow.native.reader import read_pro, slide_sequence
from worshipflow.native.theme import builtin_style
from worshipflow.native.writer import write_pro
from worshipflow.qa import run_checks
from worshipflow.workflow import Config, find_songs

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "lyrics")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return parse_lyrics(fh.read())


def roundtrip(song, style=None, opt=None):
    plan = segment_song(song, opt or SegmentOptions())
    style = style or builtin_style("standard")
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "song.pro")
    write_pro(plan, path, style, uuid_seed="test")
    desc = read_pro(path)
    report = run_checks(plan, desc, output_path=path, style_font=style.font_info)
    return plan, desc, report


def slides(plan, section=None):
    return [c.lines for c in plan.cues if section is None or c.section == section]


class FixtureTests(unittest.TestCase):
    def assertClean(self, report):
        bad = [c for c in report.checks if c.status == "fail"]
        self.assertEqual(bad, [], f"failed checks: {[(c.id, c.detail) for c in bad]}")

    def test_01_simple(self):
        plan, desc, rep = roundtrip(load("01-simple.txt"))
        self.assertEqual([g["name"] for g in desc["groups"]], ["Verse 1", "Chorus"])
        self.assertEqual(slides(plan), [["You are good", "You are kind"], ["We will sing", "We will shine"]])
        self.assertClean(rep)
        self.assertEqual(rep.state.value, "READY_FOR_IMPORT")

    def test_02_long_verse_four_slides(self):
        plan, _, rep = roundtrip(load("02-long-verse.txt"))
        self.assertEqual(len(slides(plan)), 4)
        self.assertTrue(all(len(s) == 2 for s in slides(plan)))
        self.assertClean(rep)

    def test_03_single_line_chorus(self):
        plan, _, rep = roundtrip(load("03-single-line-chorus.txt"))
        self.assertEqual(slides(plan, "Chorus"), [["Hallelujah, You are here"]])
        self.assertClean(rep)

    def test_04_repeated_bridge(self):
        plan, desc, rep = roundtrip(load("04-repeated-bridge.txt"))
        self.assertEqual(desc["arrangements"][0]["groups"], ["Verse 1"] + ["Bridge"] * 4 + ["Verse 1"])
        self.assertEqual(len(slide_sequence(desc)), 6)
        self.assertClean(rep)

    def test_05_partial_repeat_is_kept_as_note(self):
        song = load("05-partial-repeat.txt")
        self.assertEqual(song.arrangement.steps[2].partial, "last two lines")
        plan, _, rep = roundtrip(song)
        self.assertClean(rep)

    def test_06_instrumental_blank_slides(self):
        plan, desc, rep = roundtrip(load("06-instrumental.txt"))
        names = [g["name"] for g in desc["groups"]]
        self.assertEqual(names, ["Intro", "Verse 1", "Instrumental", "Chorus", "Outro"])
        intro = desc["groups"][0]["slides"]
        self.assertEqual(len(intro), 1)
        self.assertEqual(intro[0]["texts"], [])
        self.assertClean(rep)

    def test_07_bilingual_inline(self):
        plan, desc, rep = roundtrip(load("07-bilingual-inline.txt"), builtin_style("bilingual"))
        s = desc["groups"][0]["slides"][0]
        self.assertEqual(s["texts"], ["You are holy\nYou are worthy", "Tú eres santo\nTú eres digno"])
        self.assertClean(rep)

    def test_08_bilingual_parallel(self):
        song = load("08-bilingual-parallel.txt")
        self.assertEqual(song.section("Verse 1").translation_lines, ["La luz llegó", "La oscuridad huye"])
        self.assertEqual([s.name for s in song.sections], ["Verse 1", "Chorus"])
        _, desc, rep = roundtrip(song, builtin_style("bilingual"))
        self.assertEqual(desc["groups"][1]["slides"][0]["texts"], ["Jesus reigns", "Jesús reina"])
        self.assertClean(rep)

    def test_09_live_performance_order(self):
        song = load("09-live-performance-order.txt")
        self.assertEqual([s.name for s in song.sections], ["Verse 1", "Chorus", "Verse 2", "Tag"])
        self.assertEqual(song.arrangement.expanded(), ["Verse 1", "Chorus", "Verse 2", "Chorus", "Chorus", "Tag"])
        self.assertEqual(song.version.label, "Live")
        _, _, rep = roundtrip(song)
        self.assertClean(rep)

    def test_10_duplicate_titles_are_all_reported(self):
        cfg = Config(library_dirs=[FIX])
        hits = [h for h in find_songs("Same Name Song", cfg) if h["title"] == "Same Name Song"]
        self.assertEqual(len(hits), 2)
        self.assertEqual({h["version"] for h in hits}, {"Studio", "Live"})

    def test_11_missing_lyrics_rejected(self):
        with self.assertRaises(LyricParseError):
            load("12-missing-lyrics.txt")

    def test_12_wrong_version_fails_qa(self):
        song = load("09-live-performance-order.txt")
        plan = segment_song(song)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.pro")
            write_pro(plan, p)
            rep = run_checks(plan, read_pro(p), expected_version="Studio")
        self.assertEqual(next(c for c in rep.checks if c.id == "version").status, "fail")
        self.assertEqual(rep.state.value, "NEEDS_REVIEW")

    def test_13_theme_mismatch_detected(self):
        song = load("01-simple.txt")
        plan = segment_song(song)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.pro")
            write_pro(plan, p, builtin_style("youth"))
            rep = run_checks(plan, read_pro(p), style_font=builtin_style("standard").font_info)
        self.assertEqual(next(c for c in rep.checks if c.id == "theme").status, "fail")

    def test_14_import_failure_empty_and_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            empty = os.path.join(d, "empty.pro")
            open(empty, "wb").close()
            with self.assertRaises(ValueError):
                read_pro(empty)
            bad = os.path.join(d, "bad.pro")
            with open(bad, "wb") as fh:
                fh.write(b"\xff\xff\xff\xff not protobuf")
            with self.assertRaises(Exception):
                read_pro(bad)

    def test_15_long_lines_wrap_at_natural_break(self):
        plan, _, rep = roundtrip(load("13-long-lines.txt"))
        lines = [l for s in slides(plan) for l in s]
        self.assertTrue(all(len(l) <= 38 for l in lines), lines)
        self.assertEqual(" ".join(lines), "When the night is long and every road I travel seems to fade away "
                                          "You remind me of Your promise and You lead me home again")
        self.assertIn("long_line_wrapped", {f for c in plan.cues for f in c.flags})
        self.assertClean(rep)

    def test_16_odd_stanza_three_lines(self):
        plan, _, rep = roundtrip(load("14-odd-stanza.txt"))
        self.assertEqual(slides(plan), [["Rise up, rise up", "Sons and daughters", "Rise up and sing"]])
        self.assertIn("three_lines", plan.cues[0].flags)
        self.assertTrue(any("three lines" in u for u in rep.uncertainties))

    def test_17_short_lines_stack(self):
        plan, _, _ = roundtrip(load("15-short-lines.txt"))
        self.assertEqual(len(slides(plan)), 2)
        self.assertEqual(sum(len(s) for s in slides(plan)), 6)

    def test_18_explicit_breaks(self):
        plan, _, _ = roundtrip(load("16-explicit-breaks.txt"))
        self.assertEqual(slides(plan), [["One line alone"], ["Two lines here", "And here as well"]])

    def test_19_abbreviated_arrangement(self):
        song = load("17-abbrev-arrangement.txt")
        self.assertEqual(song.arrangement.expanded(),
                         ["Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", "Bridge", "Chorus", "Tag"])
        _, desc, rep = roundtrip(song)
        self.assertEqual(len(desc["arrangements"][0]["groups"]), 8)
        self.assertClean(rep)

    def test_20_unknown_arrangement_section(self):
        song = load("17-abbrev-arrangement.txt")
        with self.assertRaises(ArrangementError) as cm:
            parse_arrangement("V1, C, Pre", song)
        self.assertIn("Pre-Chorus", str(cm.exception))
        with self.assertRaises(ArrangementError):
            parse_arrangement("V3", song)

    def test_21_spanish_accents_roundtrip(self):
        song = load("18-spanish.txt")
        self.assertEqual([s.name for s in song.sections], ["Verse 1", "Chorus"])
        _, desc, rep = roundtrip(song)
        self.assertEqual(desc["groups"][1]["slides"][0]["texts"][0], "¡Aleluya! ¿Quién como tú?\nPor siempre te alabaré")
        self.assertClean(rep)

    def test_22_unauthorized_lyrics_block_readiness(self):
        _, _, rep = roundtrip(load("19-unauthorized.txt"))
        self.assertEqual(next(c for c in rep.checks if c.id == "lyrics_authorized").status, "fail")
        self.assertEqual(rep.state.value, "DRAFT")

    def test_23_chorus_with_new_words_becomes_chorus_2(self):
        song = load("20-chorus-variant.txt")
        self.assertEqual([s.name for s in song.sections], ["Verse 1", "Chorus", "Chorus 2"])

    def test_24_no_headers(self):
        song = load("21-no-headers.txt")
        self.assertEqual([s.name for s in song.sections], ["Verse 1"])
        self.assertEqual(len(song.sections[0].source_lines), 3)

    def test_25_header_styles(self):
        song = load("22-caps-colon-headers.txt")
        self.assertEqual([s.name for s in song.sections], ["Verse 1", "Chorus", "Bridge", "Pre-Chorus"])

    def test_26_one_line_per_slide(self):
        plan, _, rep = roundtrip(load("02-long-verse.txt"), opt=SegmentOptions(max_lines_per_slide=1))
        self.assertEqual(len(plan.cues), 8)
        self.assertClean(rep)

    def test_27_four_line_slides_need_review(self):
        plan, _, rep = roundtrip(load("02-long-verse.txt"), opt=SegmentOptions(max_lines_per_slide=4, max_slide_chars=200))
        self.assertIn("four_lines_review", plan.cues[0].flags)
        self.assertEqual(rep.state.value, "NEEDS_REVIEW")

    def test_28_youth_uppercase_still_matches_source(self):
        _, desc, rep = roundtrip(load("01-simple.txt"), builtin_style("youth"))
        self.assertEqual(desc["groups"][0]["slides"][0]["texts"][0], "YOU ARE GOOD\nYOU ARE KIND")
        self.assertClean(rep)

    def test_29_production_path_flagged(self):
        song = load("01-simple.txt")
        plan = segment_song(song)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.pro")
            write_pro(plan, p)
            rep = run_checks(plan, read_pro(p), output_path=p, production_paths=[d])
        self.assertEqual(next(c for c in rep.checks if c.id == "production_safe").status, "fail")

    def test_30_all_fixture_files_parse_or_fail_cleanly(self):
        for name in sorted(os.listdir(FIX)):
            with self.subTest(name=name):
                try:
                    song = load(name)
                except LyricParseError:
                    self.assertEqual(name, "12-missing-lyrics.txt")
                    continue
                roundtrip(song)


if __name__ == "__main__":
    unittest.main()
