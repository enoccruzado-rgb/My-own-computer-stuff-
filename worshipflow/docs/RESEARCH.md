# Research notes (2026-11-10)

## ProPresenter 22
- Released as build **22 (369098928)**, around Oct 14 2026, alongside ProPresenter **Cloud**. Some Renewed Vision
  posts still call it beta. Sources: https://renewedvision.com/propresenter/download,
  https://www.renewedvision.com/blog/introducing-cloud
- Show directory (v20+): `~/Library/Application Support/RenewedVision/ProPresenter/UserWorkspaces/`
  (https://support.renewedvision.com/hc/en-us/articles/360041815133). With Cloud, a whole workspace syncs,
  so writing files into it by hand is risky. WorshipFlow never does.
- Official API: see `API-CAPABILITIES.md`. **It cannot create or edit presentations**, which decides the
  approach: generate native files, import them, then verify through the API.
- Reflow Editor (https://support.renewedvision.com/hc/en-us/articles/34513457866899): Option+Return splits
  a slide. Not needed because we split slides in the file.
- Themes (https://support.renewedvision.com/hc/en-us/articles/34551484745875): applied per slide
  (right-click > Theme). On disk a theme is a folder with a `Theme` protobuf (`rv.data.Template.Document`)
  plus `Assets/`. Whether a presentation keeps a link to its theme is undocumented. The 21.4 schema has no
  theme reference on slides, so we copy the styling into each slide, the way the theme editor output looks.

## Repositories reviewed

| Repo | License | What it is | Use in WorshipFlow |
|---|---|---|---|
| greyshirtguy/ProPresenter7-Proto | MIT | Reverse-engineered .proto files, auto-updated per release (latest: 21.4) | **Used**: compiled into `native/rvproto`, copied in `third_party/` with license |
| bussnet/propresenter7-php-lib | MIT | PHP read/write for .pro, .probundle, themes, with real sample files | **Studied**: field defaults and RTF encoding mirrored; two sample files used as test inputs (with license). Needs PHP 8.4 (machine has 8.3), so not run |
| ChrisMBarr/ProPresenter-Parser | MIT | TypeScript parser for Pro4-7 | Considered as an independent validator. `npm install` of an unvetted repo was not run; used `protoc --decode` with a second schema copy instead |
| alxpark/propresenter-mcp | MIT | MCP server wrapping the HTTP API (231 endpoints, incl. triggers/clear) | Not used. It exposes live-output controls, which conflicts with our safety rules. Its README still assumes port 50000 and an API password, which the current spec does not have |
| JacobBaartse/MultiLanuageProPresenter | **no license** | Python script: clones an exported `Template.pro` for multi-language songs | Confirms the template-cloning method works in practice. **Code not reused** (no license) |
| eliogos/propresenter-plus | ISC (package.json; no LICENSE file) | TS API client + .pro builders | Not used; reviewed only |

## Licensing notes for commercial use
- MIT/ISC code: keep copyright notices (done in `third_party/`, `tests/fixtures/native/`).
- Song lyrics are copyrighted. A church can display them under its CCLI Copyright License, but that does
  not let a software vendor store or redistribute lyrics. WorshipFlow keeps lyrics only in the church's own
  library folder (git-ignored). A commercial product needs a licensing agreement (for example a CCLI or
  SongSelect partner integration) before it supplies lyrics itself.
- ProContent and Sunday Screens assets: licensed to the subscriber church. Reference them; never bundle
  or redistribute them.
- Renewed Vision: the `.pro` schema is unofficial. Do not claim partnership or endorsement. Ask Renewed
  Vision about integration terms before selling.

## YouTube / performance reference (P6, not built yet)
Lawful options: the YouTube Data API for metadata; captions only where the owner allows; audio only when
the church supplies a file it has the right to use; then forced alignment of the authorized lyrics with
Whisper-class speech recognition. Downloading YouTube audio would break YouTube's terms, so it is not planned.
Worship-leader notes always override detection.
