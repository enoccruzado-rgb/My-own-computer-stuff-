# Architecture

```
lyric sheet (.txt, authorized) ─► lyrics/parser.py ─► Song (models.py)
                                         │
leader arrangement "V1 C V2 C B x2 C" ─► arrangement.py
                                         ▼
                              lyrics/segment.py  (deterministic phrasing → SlideCue[])
                                         ▼
theme (preset | template .pro | theme folder) ─► native/theme.py ─► SlideStyle
                                         ▼
                              native/writer.py ─► song.pro  (+ plan.json, qa.json, preview.txt)
                                         ▼
                              native/reader.py ─► qa.py (file-level checks, readiness state)
                                         ▼
       person imports into a TEST library (File > Import) on the church Mac
                                         ▼
       propresenter_api.py verify_live: GET presentation / saved file / thumbnails ─► qa.py
                                         ▼
       person approves (CLI) ─► workflow.publish ─► allowed folder + audit.log
```

Entry points: `cli.py` (`python -m worshipflow`), `mcp_server.py` (stdio MCP, 22 tools),
`.claude/skills/worshipflow/SKILL.md`.

Design rules:
- Exact lyrics are stored once (`SongSection.source_lines`); slides only group them. QA proves the words
  on screen equal the source words.
- Rules first (segmentation is deterministic and tested). AI help can be layered on top later, but it
  may only re-group lines, never change words.
- Nothing in the codebase can trigger output, clear layers or write into ProPresenter's workspace folder.
