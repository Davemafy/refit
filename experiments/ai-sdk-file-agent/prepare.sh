#!/usr/bin/env bash
set -euo pipefail
DEST="${1:?Specify a new ZIP file path}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
git -C "$TEMP" init -q
git -C "$TEMP" fetch -q --depth=1 https://github.com/AdamT3H/AI-Lab1.git e13a6ff71e262152cca58dcd1d050d8c376c3115
git -C "$TEMP" archive --format=tar FETCH_HEAD src/agent/agent-aisdk.ts src/agent/tools.ts src/models.ts | tar -xf - -C "$TEMP"
python3 - "$TEMP" "$HERE" "$DEST" <<'PY'
from pathlib import Path
import sys
from zipfile import ZipFile

source, here, dest = map(Path, sys.argv[1:])
with ZipFile(dest, "x") as zip_file:
    for name in ("src/agent/agent-aisdk.ts", "src/agent/tools.ts", "src/models.ts"):
        zip_file.write(source / name, name)
    zip_file.write(here / "invoke.ts", "invoke.ts")
    zip_file.write(here.parents[1] / "integrations/openai-compatible/tool-structured-output.mjs",
                   "tool-structured-output.mjs")
    zip_file.writestr("package.json", '{"type":"module","dependencies":{"ai":"^7.0.127","@ai-sdk/google":"^4.0.87","@ai-sdk/openai-compatible":"^3.0.62","ollama-ai-provider-v2":"^4.0.1","zod":"^4.5.4"}}')
    for name, value in (("order", "RFT-ORDER-274"), ("invoice", "RFT-INVOICE-618"), ("receipt", "RFT-RECEIPT-943")):
        zip_file.writestr("records/" + name + ".txt", value)
PY
