# ProPresenter 22 capabilities (checked 2026-11-10)

Status key: **CONFIRMED** (official source or tested here), **UNTESTED** (documented but not yet run
against the church's ProPresenter), **EXPERIMENTAL** (works in files here, not yet opened in ProPresenter 22),
**UNAVAILABLE** (does not exist).

| Capability | How | Status | Evidence |
|---|---|---|---|
| ProPresenter 22 exists | build 22 (369098928) | CONFIRMED | https://renewedvision.com/propresenter/download |
| Local HTTP API | `http://<mac>:50001`, Settings > Network > Enable Network | CONFIRMED (docs), UNTESTED here | https://openapi.propresenter.com/ (snapshot: `propresenter-openapi-snapshot.js`) |
| API authentication | none in the spec | CONFIRMED | spec has no `securitySchemes` (so never expose the port to the internet) |
| Create a presentation via API | - | **UNAVAILABLE** | no endpoint |
| Edit slide text / groups / arrangements via API | - | **UNAVAILABLE** | read only: `GET /v1/presentation/{uuid}` |
| Apply a theme to a presentation via API | - | **UNAVAILABLE** | only `PUT /v1/theme/{id}/slides/{theme_slide}` edits a theme itself |
| Import a .pro via API | - | **UNAVAILABLE** | no endpoint |
| List libraries / presentations | `GET /v1/libraries`, `GET /v1/library/{id}` | CONFIRMED (docs), UNTESTED | used by `doctor`, `verify --live` |
| Read a presentation (groups, slide text, file path) | `GET /v1/presentation/{uuid}` | CONFIRMED (docs), UNTESTED | used by `verify --live` |
| Slide thumbnails | `GET /v1/presentation/{uuid}/thumbnail/{index}` | CONFIRMED (docs), UNTESTED | used by `verify --live` |
| List themes | `GET /v1/themes`, `GET /v1/theme/{id}` | CONFIRMED (docs), UNTESTED | `worshipflow themes` |
| Playlists | `GET/POST /v1/playlists`, `PUT /v1/playlist/{id}` (replace items) | CONFIRMED (docs), UNTESTED | client method exists, not wired to publish yet |
| Write a native .pro song (groups, slides, arrangement, CCLI) | protobuf `rv.data.Presentation` | EXPERIMENTAL | 41+ tests here; decodes with two independent schema sets; **not yet opened in ProPresenter 22** |
| Clone styling from an exported song | template `.pro` | EXPERIMENTAL | tested on a file written by ProPresenter 20 |
| Clone styling from a theme folder | `Theme` file = `rv.data.Template.Document` | EXPERIMENTAL | tested on a ProPresenter 18.2 theme |
| Import a .pro via File > Import / drag into library | manual | UNTESTED for v22 | standard ProPresenter workflow; to confirm on the church Mac |
| Opening a .pro with `open -a ProPresenter` | macOS | UNTESTED | behaviour unknown (import dialog vs. direct add); off by default |
| Dropping files into the workspace folder while running | - | UNTESTED, **not used** | unsafe with Cloud sync; we never write into `~/Library/Application Support/RenewedVision` |
| Reflow Editor automation | Option+Return splits slides | CONFIRMED (docs), not automated | not needed: slides are split in the file |
| ProPresenter Cloud API | - | UNAVAILABLE | no public API found; Cloud syncs whole workspaces |
| Accessibility (UI) automation | - | NOT STARTED | only if native import proves unreliable |
