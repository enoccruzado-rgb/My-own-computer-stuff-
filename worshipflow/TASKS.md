# Tasks (priority order)

## Done
- [x] Research the API and file format; capability table (docs/API-CAPABILITIES.md)
- [x] Review the six repositories, including licenses (docs/RESEARCH.md)
- [x] Python schema compiled from the 21.4 protos
- [x] Song model, lyric parser (headers, performance order, bilingual, repeat markers)
- [x] Deterministic segmentation (1-2 lines, natural wraps, 3-line and 4-line flags)
- [x] Arrangement parser (abbreviations, x2, partial notes, helpful errors)
- [x] Native .pro writer and reader; RTF encode/decode
- [x] Themes: 4 built-in presets, cloning from a template song or a theme folder
- [x] QA engine with readiness states; honest `not_run` for checks that need ProPresenter
- [x] CLI, MCP server (22 tools), Claude Code skill, approval/publish with audit log
- [x] 42 tests, original demo songs (English + bilingual)
- [x] Mac acceptance script

## Next
1. [ ] **P0 acceptance on the church Mac** (B1): run `scripts/mac-acceptance-test.sh`, record the results here and
   in TEST_RESULTS.md. If ProPresenter rejects the file, compare a ProPresenter-22-exported song with ours using
   `worshipflow inspect` and fix the differences.
2. [ ] Export one church-styled song and the "normal" theme (B2); make it `default_theme`; verify with thumbnails.
3. [ ] Confirm what `/v1/presentation/{uuid}` returns for bilingual slides (one text or two) and adjust `verify_live`.
4. [ ] Link groups to ProPresenter's global groups (`application_group_identifier`) using the `Groups` library file, read only.
5. [ ] Optional: add to a playlist after approval (`PUT /v1/playlist/{id}`), with a dry-run diff first.
6. [ ] `.probundle` output (song plus background media).
7. [ ] P6: rehearsal-notes parser ("C x2 after bridge, tag 3x") → arrangement; then lawful audio alignment.
8. [ ] P7: remote access through an authenticated private network (e.g. Tailscale) to a local agent. Never expose port 50001.
9. [ ] P8: commercial roadmap (multi-tenant, billing) only after P0-P4 are proven.
