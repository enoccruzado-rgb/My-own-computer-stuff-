#!/bin/bash
# Regenerate worshipflow/native/rvproto from third_party/propresenter7-proto.
# Needs: pip install grpcio-tools (in a scratch venv). Update third_party from
# https://github.com/greyshirtguy/ProPresenter7-Proto/tree/main/autogen-proto first.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=worshipflow/native/rvproto
PY="${PROTOC_PY:-python3}"
rm -f "$OUT"/*_pb2.py
(cd third_party/propresenter7-proto && "$PY" -m grpc_tools.protoc -I. --python_out="../../$OUT" ./*.proto)
sed -i.bak -E 's/^import ([A-Za-z0-9_]+_pb2) as /from . import \1 as /' "$OUT"/*_pb2.py && rm -f "$OUT"/*.bak
touch "$OUT/__init__.py"
echo "regenerated from ProPresenter $(cat third_party/propresenter7-proto/version.txt)"
