# Test results

## 2026-11-10 - cloud dev container (Linux, Python 3.13, protobuf 7.36.2). No ProPresenter available.

`../.venv/bin/python -m unittest discover -s tests -t .` → **42 tests, all pass** (also clean with `-W error::ResourceWarning`).

| Area | Result |
|---|---|
| 22 lyric fixtures (simple, long verse, single-line chorus, repeated bridge, partial repeat, instrumental, bilingual inline + parallel, live performance order, duplicate titles, missing lyrics, long lines, odd stanza, short lines, explicit breaks, abbreviations, Spanish accents, unauthorized source, chorus variant, no headers, header styles) | pass |
| Wrong version, theme mismatch, empty/corrupt .pro, production path, 4-line slides → correctly flagged | pass |
| Reading a real ProPresenter 20 file (groups, slide text, arrangement) | pass |
| RTF round trip on every text in 16 real ProPresenter files + accents/emoji | pass |
| Styling cloned from a real ProPresenter theme (OpenSans-Bold 60pt + background layer) and from a real exported song | pass |
| Prepare → approve → publish, with refusals for unapproved, tampered, overwrite, disallowed folder | pass |
| MCP server over stdio with a real MCP client (22 tools; create, re-arrange, honest failure when ProPresenter is unreachable) | pass |
| Independent decode of a generated song with `protoc --decode rv.data.Presentation` using a second schema copy (bussnet, 19beta-based) | pass, no unknown fields |

## Not run (needs the church Mac with ProPresenter 22)
- Import/open in ProPresenter 22, editable text in the editor, groups/arrangement in the UI
- Thumbnails, save + reopen persistence, visual overflow on the real LED wall
- Status of acceptance test: **NOT PASSED YET** (blocked by B1). Run `scripts/mac-acceptance-test.sh`.
