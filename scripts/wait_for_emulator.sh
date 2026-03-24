#!/usr/bin/env bash
# wait_for_emulator.sh
# Poll the Android emulator container until it is fully booted.
#
# Usage:
#   ./scripts/wait_for_emulator.sh [container_name] [timeout_seconds]
#
# Defaults:
#   container_name  = android-emulator
#   timeout_seconds = 300

set -euo pipefail

CONTAINER="${1:-android-emulator}"
TIMEOUT="${2:-300}"
INTERVAL=10

echo "⏳ Waiting for Android emulator in container '${CONTAINER}' to be ready …"
echo "   (timeout: ${TIMEOUT}s)"

elapsed=0
while true; do
    status=$(docker exec "${CONTAINER}" cat /device_status 2>/dev/null || echo "")
    if echo "${status}" | grep -q "device"; then
        echo "✅ Emulator is ready (status: ${status})"
        break
    fi

    if [ "${elapsed}" -ge "${TIMEOUT}" ]; then
        echo "❌ Timed out waiting for emulator after ${TIMEOUT}s." >&2
        exit 1
    fi

    echo "   … still waiting (${elapsed}s elapsed, status='${status}')"
    sleep "${INTERVAL}"
    elapsed=$((elapsed + INTERVAL))
done

# Verify ADB can see the device
echo ""
echo "🔍 Connected ADB devices:"
docker exec "${CONTAINER}" adb devices
