#!/usr/bin/env bash
# start_emulator.sh — Launch the Android emulator and wait until it has fully booted.
set -euo pipefail

BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"   # seconds to wait for boot
POLL_INTERVAL=5

echo "[start_emulator.sh] Launching emulator (device: ${EMULATOR_DEVICE:-default})..."

# budtmo/docker-android exposes the emulator via supervisord; it is already
# started by the base image's own entrypoint.  We only need to wait for ADB
# to report that the boot sequence has finished.
echo "[start_emulator.sh] Waiting for emulator to boot (timeout: ${BOOT_TIMEOUT}s)..."

elapsed=0
while true; do
    boot_completed="$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '[:space:]')" || true
    if [ "${boot_completed}" = "1" ]; then
        echo "[start_emulator.sh] Emulator booted successfully."
        break
    fi

    if [ "${elapsed}" -ge "${BOOT_TIMEOUT}" ]; then
        echo "[start_emulator.sh] ERROR: Emulator did not boot within ${BOOT_TIMEOUT} seconds." >&2
        exit 1
    fi

    sleep "${POLL_INTERVAL}"
    elapsed=$(( elapsed + POLL_INTERVAL ))
done

# Unlock the screen in case it is locked
adb shell input keyevent 82 || true
