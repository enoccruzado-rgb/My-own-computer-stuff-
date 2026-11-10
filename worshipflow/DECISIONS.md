# Decisions

1. **Native .pro generation, not the API, for authoring** (2026-11-10). The official API has no create or
   edit endpoints for presentations, groups, arrangements or themes. Evidence: docs/API-CAPABILITIES.md.
2. **Python + protobuf** (2026-11-10). The repo already uses Python and the `mcp` package. The protobuf
   runtime is official and fast, and greyshirtguy's schema compiles cleanly.
3. **Schema 21.4** (2026-11-10). This is the newest published schema (ProPresenter 22's is not out yet). We stamp
   files as 21.4. ProPresenter normally opens files from older versions. To confirm on 22.
4. **Clone styling instead of rebuilding a design engine** (2026-11-10). A church-styled template song gives
   the most faithful look. A theme folder comes next, then built-in presets as a fallback.
5. **Deterministic segmentation first** (2026-11-10). It is predictable, testable and never changes words. Any
   AI help later may only re-group lines.
6. **Import by a person into a test library** (2026-11-10). Writing into ProPresenter's workspace while it
   runs (and with Cloud sync) is undocumented and risky. `open -a ProPresenter` is behind a config flag
   until it has been tested.
7. **Approval is not an MCP tool** (2026-11-10). A person runs `worshipflow approve --by`. The approval is bound
   to the file's SHA-256, and any later change voids it.
8. **No third-party ProPresenter MCP with trigger/clear tools** (2026-11-10). This avoids any path to the LED wall.
