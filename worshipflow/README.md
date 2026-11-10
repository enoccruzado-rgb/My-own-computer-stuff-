# WorshipFlow AI

Turns an authorized lyric sheet into a **native, editable ProPresenter song**: groups (Verse, Chorus,
Bridge...), slides split into natural 1-2 line phrases, the arrangement, and your theme. Then it checks the
result and stages it for import. It never touches the live screens.

> Status: the software is built and tested (42 tests). It has **not yet been opened in ProPresenter 22**,
> so that is the next step on the church Mac mini (see `PROGRESS.md`).

## Try it
```bash
cd worshipflow
../.venv/bin/python -m worshipflow analyze songs/demo/morning-light.txt                 # plan only
../.venv/bin/python -m worshipflow prepare songs/demo/morning-light.txt --arrangement "V1 C V2 C B C"
../.venv/bin/python -m worshipflow preview out/morning-light-worshipflow-demo.pro
../.venv/bin/python -m worshipflow doctor                                               # ProPresenter connection
```
`prepare` writes `out/<song>.pro` plus `.plan.json`, `.qa.json` (machine-readable QA) and `.preview.txt`.

Themes (`--theme`): `standard`, `cinematic`, `youth`, `bilingual`, a path to a song you already styled
(`My Styled Song.pro`), or a ProPresenter theme folder (`"/path/Theme Folder::Lyrics"`).

## Use it from Claude Code
The `worshipflow` MCP server is in the repo's `.mcp.json`, and the skill is at `.claude/skills/worshipflow/`.
Open Claude Code in the repo and say, for example: *"Prepare Morning Light for Sunday, V1 C V2 C B C, standard theme."*

## On the church Mac
1. ProPresenter > Settings > Network: turn on **Enable Network** (port 50001). Keep it on the church network only.
2. `cp worshipflow.config.example.json worshipflow.config.json` and edit the paths.
3. Run `scripts/mac-acceptance-test.sh` at a quiet time. Import into a **test** library only.

## Safety
- No code path triggers slides, clears layers or changes looks.
- Drafts never go into ProPresenter's workspace folder. People import them by hand into a test library.
- Approval is done by a person (`worshipflow approve file.pro --by "Name"`), is tied to the exact file, and
  is cleared by any change. Publishing refuses to overwrite unless told to, and is written to `out/audit.log`.
- Lyrics: only from the church's authorized library (`songs/library/`, kept out of git).

Docs: `docs/ARCHITECTURE.md`, `docs/API-CAPABILITIES.md`, `docs/NATIVE-FORMAT.md`, `docs/RESEARCH.md`.
Not affiliated with or endorsed by Renewed Vision. The `.pro` schema is unofficial (greyshirtguy/ProPresenter7-Proto, MIT).
