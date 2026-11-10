#!/bin/bash
# WorshipFlow acceptance test - run on the church Mac mini, NOT during a service.
# It never touches the LED wall: no slide is triggered, nothing is cleared.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python3}"

echo "== 0. Safety check =="
read -r -p "Is a service or rehearsal running right now? (y/N) " live
[[ "$live" =~ ^[Yy] ]] && { echo "Stopping. Run this when nothing is live."; exit 1; }

echo "== 1. Doctor (ProPresenter > Settings > Network > Enable Network must be on) =="
$PY -m worshipflow doctor

echo "== 2. Build the original demo song =="
$PY -m worshipflow prepare songs/demo/morning-light.txt ${THEME:+--theme "$THEME"}
PRO="out/morning-light-worshipflow-demo.pro"
$PY -m worshipflow preview "$PRO"

echo "== 3. Import into a TEST library by hand =="
cat <<MSG
In ProPresenter:
  1. Create (or select) a library named "WorshipFlow Test" - NOT your main library.
  2. File > Import > File... and choose: $(pwd)/$PRO
     (or drag the file onto the "WorshipFlow Test" library)
  3. Click the song, check groups (Verse 1, Chorus, Verse 2, Bridge) and the arrangement "Sunday".
  4. Click into a slide's text to confirm it is editable. Press Cmd+S, close and reopen ProPresenter.
MSG
read -r -p "Press Return when the song is imported and ProPresenter is open again... "

echo "== 4. Verify inside ProPresenter (reads text, saved file and thumbnails over the API) =="
$PY -m worshipflow verify "$PRO" --live | tee out/acceptance-result.json
echo "Thumbnails saved in ${PRO%.pro}.thumbs/ - open them to check the look."
echo "Send out/acceptance-result.json back so the results can be recorded in TEST_RESULTS.md."
