# Blockers

| # | Blocker | Needed from | Unblocks |
|---|---|---|---|
| B1 | No ProPresenter 22 in the cloud dev container (it is Linux). The acceptance test needs the church Mac mini. | Enoc: run `worshipflow/scripts/mac-acceptance-test.sh` on the Mac mini at a quiet time and send back `out/acceptance-result.json` plus the thumbnails | P0 milestone, checks 10/12/13 |
| B2 | No church theme or styled template song yet | Export one well-formatted song from ProPresenter (right-click > Export > .pro) and/or copy the theme folder | P3 "church normal theme" |
| B3 | No authorized lyric library yet | Approved lyric sheets (for example SongSelect exports) in `worshipflow/songs/library/` on the Mac | Real songs such as "Gratitude" |
| B4 | ProPresenter 22 protobuf schema not published yet (latest is 21.4) | Upstream (greyshirtguy) | Exact v22 field coverage |
