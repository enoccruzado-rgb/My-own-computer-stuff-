---
name: worshipflow
description: Build native, editable ProPresenter song presentations (groups, slides, arrangement, theme) from authorized lyrics, then check and stage them for import. Use when someone asks to create, fix, re-arrange, restyle or check a worship song for ProPresenter, or to prepare Sunday's songs.
---

# WorshipFlow: songs for ProPresenter

Tools come from the `worshipflow` MCP server (`.mcp.json`). The same steps exist as a CLI:
`PYTHONPATH=worshipflow .venv/bin/python -m worshipflow <command>`.

## Hard rules
1. **Only authorized lyrics.** Find the song with `song_find`. If it is not in the library, ask the
   worship leader for approved lyrics (a lyric sheet or SongSelect export). Never type lyrics from memory,
   from a YouTube video, or from a lyrics website. Never "fix" or reword lyrics.
2. **Never approve for people.** `song_request_approval` shows the reviewer what to check. A person runs
   `worshipflow approve <file.pro> --by "Name"`. Do not run that command yourself.
3. **Never touch the live show.** No tool triggers slides or clears screens. Do not use other
   ProPresenter tools (for example a third-party ProPresenter MCP) to trigger or clear anything.
4. **Drafts only go to the drafts folder.** Publishing copies an approved, unchanged file into a folder
   listed in `publish_dirs`. It never overwrites unless the person explicitly says so.
5. **Be honest about checks.** `native_import`, `thumbnails` and `persistence` stay `not_run` until
   `propresenter_verify_song(live=True)` runs on the church Mac. Say so. Never call a song verified
   without that.

## Steps
1. `song_find("<title>")`. If there are several hits (same title, different versions), ask which
   version they are singing.
2. Get the arrangement from the leader, e.g. `V1, C, V2, C, B x2, C, Tag`. Check it with
   `song_analyze_arrangement`. If the leader gave none, use the order in the lyric sheet and say so.
3. Dry run with `propresenter_create_song(..., dry_run=True)`. Show the slide preview. Point out
   three-line slides, wrapped long lines and removed `(x2)` markers.
4. Build it with `propresenter_create_song(..., dry_run=False, theme=...)`. Themes, from best to
   fallback:
   - a song the church already styled, exported as `.pro` (gives the most faithful look);
   - a ProPresenter theme folder, written `folder::Slide Name`;
   - a built-in preset: `standard`, `cinematic`, `youth` or `bilingual`.
5. Show the QA result (`song_quality_report`) in plain words: what passed, what needs a look.
6. Stage it with `propresenter_import_to_test_library`. Then the person imports it into a **test**
   library with File > Import. After that, run `propresenter_verify_song(live=True)`.
7. `song_request_approval`. After a person approves, `song_publish` to the agreed folder.

## Lyric sheet format
```
---
title: Song Title
artist: Artist
version: Live
source: church_library      # church_library | user_supplied | ccli_songselect | public_domain | original
authorized: true
ccli: 1234567
arrangement: V1, C, V2, C, B, C
---
[Verse 1]
line one
line two

line three                  # a blank line forces a new slide
[Chorus]
English line || Línea en español    # bilingual pair
```
