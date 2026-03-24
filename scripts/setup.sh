#!/usr/bin/env bash
# setup.sh
# One-shot orchestration script that:
#   1. Verifies KVM is available
#   2. Starts the Docker Compose services
#   3. Waits for the Android emulator to boot
#   4. Installs the OpenClaw APK via ADB
#   5. Sets up ADB port forwarding so the gateway can reach the Android device
#   6. Confirms the OpenClaw gateway is reachable
#
# Usage:
#   OPENCLAW_GATEWAY_TOKEN=<token> [OPENCLAW_APK_URL=<url>] ./scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "═══════════════════════════════════════════════════════════════"
echo " OpenClaw batch-pipeline setup"
echo "═══════════════════════════════════════════════════════════════"

# ── 0. Preflight checks ───────────────────────────────────────────────────────

echo ""
echo "🔍 Checking KVM availability …"
if [ ! -e /dev/kvm ]; then
    echo "❌ /dev/kvm not found. Enable KVM (nested virtualisation) on this host." >&2
    exit 1
fi
echo "   ✅ /dev/kvm present."

if ! command -v docker &>/dev/null; then
    echo "❌ 'docker' not found in PATH. Install Docker Engine first." >&2
    exit 1
fi
echo "   ✅ Docker found: $(docker --version)"

# ── 1. Start services ─────────────────────────────────────────────────────────

echo ""
echo "🐳 Starting Docker Compose services …"
docker compose up -d

# ── 2. Wait for emulator ──────────────────────────────────────────────────────

echo ""
bash "${SCRIPT_DIR}/wait_for_emulator.sh"

# ── 3. Install OpenClaw APK ───────────────────────────────────────────────────

echo ""
echo "📲 Installing OpenClaw APK …"
bash "${SCRIPT_DIR}/install_openclaw.sh"

# ── 4. ADB port forwarding ────────────────────────────────────────────────────
#
# The OpenClaw gateway runs on port 18789 inside the OpenClaw app / gateway
# container. Forward the emulator's port 18789 to the host so the Python
# pipeline can reach it directly at http://localhost:18789.

echo ""
echo "🔁 Setting up ADB port forwarding (device:18789 → host:18789) …"
docker exec android-emulator bash -c "
    adb wait-for-device
    adb forward tcp:18789 tcp:18789 2>/dev/null || true
    echo '   Forwarded rules:'
    adb forward --list
"

# ── 5. Wait for OpenClaw gateway ──────────────────────────────────────────────

echo ""
echo "⏳ Waiting for OpenClaw gateway to be ready at http://localhost:18789 …"
GATEWAY_TIMEOUT=120
elapsed=0
while true; do
    if curl -sf "http://localhost:18789/health" &>/dev/null; then
        echo "   ✅ Gateway is up."
        break
    fi
    # Some gateway versions do not expose /health; fall back to a 401/403 on
    # the completions endpoint as a sign that the server is listening.
    HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN:-changeme}" \
        "http://localhost:18789/v1/chat/completions" 2>/dev/null || true)
    if [[ "${HTTP_CODE}" =~ ^(200|400|401|403|422)$ ]]; then
        echo "   ✅ Gateway is up (HTTP ${HTTP_CODE})."
        break
    fi

    if [ "${elapsed}" -ge "${GATEWAY_TIMEOUT}" ]; then
        echo "❌ Timed out waiting for gateway after ${GATEWAY_TIMEOUT}s." >&2
        exit 1
    fi
    echo "   … (${elapsed}s, HTTP ${HTTP_CODE:-n/a})"
    sleep 10
    elapsed=$((elapsed + 10))
done

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " ✅ Setup complete!"
echo ""
echo " Next steps:"
echo "   python run_pipeline.py                   # run with default prompts.csv"
echo "   python run_pipeline.py --prompts my.csv  # run with a custom CSV"
echo "═══════════════════════════════════════════════════════════════"
