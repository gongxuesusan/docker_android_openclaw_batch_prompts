#!/usr/bin/env bash
# install_openclaw.sh — Install the OpenClaw APK onto the running emulator,
# then launch the app and wait for its gateway activity to appear.
set -euo pipefail

APK="${OPENCLAW_APK:-/app/openclaw.apk}"
PACKAGE="com.openclaw"                        # adjust if the package name differs
GATEWAY_ACTIVITY=".GatewayActivity"          # adjust if the activity name differs
LAUNCH_TIMEOUT="${LAUNCH_TIMEOUT:-30}"        # seconds to wait for the activity

# ── Install ──────────────────────────────────────────────────────────────────
if [ ! -f "${APK}" ]; then
    echo "[install_openclaw.sh] ERROR: APK not found at '${APK}'." >&2
    echo "[install_openclaw.sh] Mount the APK into the container or set OPENCLAW_APK." >&2
    exit 1
fi

echo "[install_openclaw.sh] Installing ${APK}..."
adb install -r "${APK}"
echo "[install_openclaw.sh] Installation complete."

# ── Open the gateway ─────────────────────────────────────────────────────────
echo "[install_openclaw.sh] Launching OpenClaw gateway..."
adb shell am start -n "${PACKAGE}/${PACKAGE}${GATEWAY_ACTIVITY}"

# Wait until the gateway activity is in the foreground
elapsed=0
poll=2
while true; do
    current="$(adb shell dumpsys activity activities 2>/dev/null \
                | grep -o "mResumedActivity.*" \
                | head -1 || true)"
    if echo "${current}" | grep -q "${PACKAGE}"; then
        echo "[install_openclaw.sh] Gateway activity is active."
        break
    fi

    if [ "${elapsed}" -ge "${LAUNCH_TIMEOUT}" ]; then
        echo "[install_openclaw.sh] WARNING: Gateway activity not confirmed after ${LAUNCH_TIMEOUT}s; continuing anyway."
        break
    fi

    sleep "${poll}"
    elapsed=$(( elapsed + poll ))
done
