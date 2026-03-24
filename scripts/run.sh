#!/usr/bin/env bash
# run.sh — Main entrypoint: start emulator, install OpenClaw, run batch prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[run.sh] Starting Android emulator..."
"${SCRIPT_DIR}/start_emulator.sh"

echo "[run.sh] Installing OpenClaw..."
"${SCRIPT_DIR}/install_openclaw.sh"

echo "[run.sh] Running batch prompts..."
python3 "${SCRIPT_DIR}/batch_prompts.py"

echo "[run.sh] Done. Results written to ${OUTPUT_FILE}."
