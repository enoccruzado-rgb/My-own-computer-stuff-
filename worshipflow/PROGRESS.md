# Progress / handoff

**Current objective:** P0, a real native song verified inside ProPresenter 22.

**State (2026-11-10):** Everything that can be built and tested without ProPresenter is done and tested
(42 tests pass). The official API cannot author songs (confirmed in the spec), so WorshipFlow writes native
`.pro` files and uses the API only to verify. The demo song `songs/demo/morning-light.txt`
(Verse 1, Chorus, Verse 2, Chorus, Bridge, Chorus) builds to 8 unique slides, 12 slides in performance order.

**Not yet proven:** that ProPresenter 22 opens our file. This is the single most important open item.

**Next executable action:** on the church Mac mini, at a quiet time:
```
cd My-own-computer-stuff-
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd worshipflow && PY=../.venv/bin/python scripts/mac-acceptance-test.sh
```
Then record `out/acceptance-result.json` in TEST_RESULTS.md.

**If the import fails:** export any song from ProPresenter 22 to `.pro`, run `worshipflow inspect` on both files,
and compare the fields (application_info, cue structure, element fields). Try `--theme <exported.pro>` too: it
clones a ProPresenter-22-written slide, which is the most likely fix.
