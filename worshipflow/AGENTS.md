# Instructions for AI agents working on WorshipFlow

Start of every session:
1. Read this file, then PROGRESS.md, TASKS.md, BLOCKERS.md, TEST_RESULTS.md.
2. `git status`, and run the tests:
   `cd worshipflow && ../.venv/bin/python -m unittest discover -s tests -t .`
3. Continue the highest-priority open task in TASKS.md.

Rules:
- Never put copyrighted lyrics in the repo. Test lyrics must be original or public domain.
- Never write into ProPresenter's workspace folder or a production library. Never trigger output or clear
  layers. Use a test library for every experiment, and never during a service.
- Never mark a check as passed without running it. `native_import`, `thumbnails` and `persistence` need
  the church Mac.
- Keep the lyric text exact. Segmentation may group or wrap lines, never change words.
- Regenerating `native/rvproto`: see docs/NATIVE-FORMAT.md (protoc from grpcio-tools, then rewrite the
  imports to relative imports).
- Update PROGRESS.md and TEST_RESULTS.md before you stop.
