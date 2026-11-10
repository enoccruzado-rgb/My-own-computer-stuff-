# The native .pro format (what WorshipFlow writes)

A `.pro` file is one protobuf message, `rv.data.Presentation`. The schema is unofficial and
reverse-engineered (greyshirtguy/ProPresenter7-Proto, MIT). We compile the **21.4** set
(`third_party/propresenter7-proto`, `version.txt`) into `worshipflow/native/rvproto/`.

```
Presentation
├─ application_info      platform macOS, app version 21.4 (build 352583705)
├─ uuid, name, category="Song", notes
├─ cue_groups[]          one per song section ("Verse 1", "Chorus" ...)
│   ├─ group {uuid, name, color, hotKey}
│   └─ cue_identifiers[] the section's slide UUIDs, in order
├─ cues[]                one per slide
│   └─ actions[0] type=ACTION_TYPE_PRESENTATION_SLIDE
│       └─ slide.presentation.base_slide {uuid, size 1920x1080, elements[]}
│           └─ elements[i].element {uuid, name, bounds, path, fill, stroke, shadow, feather,
│                                    text {attributes(font, fill, paragraph), rtf_data, vertical_alignment}}
├─ arrangements[]        {uuid, name="Sunday", group_identifiers[] (repeats allowed)}
├─ selected_arrangement  -> the arrangement above
└─ ccli                  author, song title, publisher, year, song number
```

Element order matters: index 0 is the frontmost layer. We write lyrics, then translation, then the
theme's decoration layers (backgrounds, shapes).

Slide text is CocoaRTF (`\ansicpg1252`). Lines inside one text box are RTF soft returns (`\` + newline).
Non-ASCII is escaped as `\'xx` (Windows-1252) or `\uN?`. Our encoder/decoder round-trips every text
in the reference files plus accents, curly quotes and emoji (`tests/test_native.py`).

Theme cloning keeps the church's own formatting: we take the template text box, keep its RTF header
and every control word before the words begin (`rtf.body_prefix`), and swap only the words.

Known limits:
- The schema is unofficial. ProPresenter 22 may add fields; unknown fields from a template are kept as-is
  when we deep-copy elements, but we cannot read their meaning.
- `application_group_identifier` (the link to ProPresenter's global group list) is not set; ProPresenter
  should show the group names and colors anyway. To confirm on the church Mac.
- We do not yet write `.probundle` (song + media). Backgrounds that are media files are not embedded.

## Regenerating the Python schema
`PROTOC_PY=/path/to/venv-with-grpcio-tools/bin/python scripts/regen_proto.sh`. When greyshirtguy's
repository publishes a ProPresenter 22 schema, update `third_party/propresenter7-proto`, regenerate,
and run the tests.
