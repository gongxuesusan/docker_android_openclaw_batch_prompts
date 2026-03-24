#!/usr/bin/env bash
# install_openclaw.sh
# Download the OpenClaw Android APK and install it inside the emulator via ADB.
#
# The APK download instructions are published at:
#   https://gist.github.com/alisolanki/84422f89575970eac848f552af188816
#
# Usage:
#   OPENCLAW_APK_URL=<url> ./scripts/install_openclaw.sh [container_name]
#
# If OPENCLAW_APK_URL is not set the script will look for a pre-downloaded
# openclaw.apk in the repository root, or attempt to pull the latest release
# APK from the OpenClaw GitHub releases page.

set -euo pipefail

CONTAINER="${1:-android-emulator}"
APK_LOCAL="/tmp/openclaw.apk"

# ── 1. Resolve the APK ────────────────────────────────────────────────────────

if [ -n "${OPENCLAW_APK_URL:-}" ]; then
    echo "📥 Downloading OpenClaw APK from: ${OPENCLAW_APK_URL}"
    curl -fsSL -o "${APK_LOCAL}" "${OPENCLAW_APK_URL}"
elif [ -f "openclaw.apk" ]; then
    echo "📦 Using local openclaw.apk found in the project root."
    APK_LOCAL="openclaw.apk"
else
    # Fallback: latest APK from the OpenClaw GitHub releases
    LATEST_APK_URL=$(
        curl -fsSL "https://api.github.com/repos/openclaw/openclaw/releases/latest" \
            | python3 -c "
import sys, json
data = json.load(sys.stdin)
for asset in data.get('assets', []):
    if asset['name'].endswith('.apk'):
        print(asset['browser_download_url'])
        break
"
    )

    if [ -z "${LATEST_APK_URL:-}" ]; then
        echo ""
        echo "⚠️  Could not automatically locate the OpenClaw APK." >&2
        echo "   Please follow the instructions at:" >&2
        echo "   https://gist.github.com/alisolanki/84422f89575970eac848f552af188816" >&2
        echo "   to obtain openclaw.apk, place it in the project root, then re-run" >&2
        echo "   this script." >&2
        exit 1
    fi

    echo "📥 Downloading OpenClaw APK from GitHub releases: ${LATEST_APK_URL}"
    curl -fsSL -o "${APK_LOCAL}" "${LATEST_APK_URL}"
fi

# ── 2. Copy APK into the container and install via ADB ────────────────────────

echo ""
echo "📤 Pushing APK to container '${CONTAINER}' …"
docker cp "${APK_LOCAL}" "${CONTAINER}:/tmp/openclaw.apk"

echo "📲 Installing APK via ADB …"
docker exec "${CONTAINER}" bash -c "
    set -euo pipefail
    adb wait-for-device
    adb install -r /tmp/openclaw.apk
"

echo ""
echo "✅ OpenClaw APK installed successfully."
echo ""
echo "🔍 Installed packages matching 'openclaw':"
docker exec "${CONTAINER}" bash -c "adb shell pm list packages | grep -i openclaw || echo '  (none found – check package name)'"

# ── 3. Launch the OpenClaw app ────────────────────────────────────────────────

echo ""
echo "🚀 Launching OpenClaw …"
docker exec "${CONTAINER}" bash -c "
    # Discover the package name dynamically
    PKG=\$(adb shell pm list packages | grep -i openclaw | head -1 | sed 's/package://')
    if [ -z \"\${PKG}\" ]; then
        echo '⚠️  OpenClaw package not found; launch skipped.' >&2
        exit 0
    fi
    echo \"   Package: \${PKG}\"
    LAUNCHER=\$(adb shell cmd package resolve-activity --brief --components -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \${PKG} 2>/dev/null | tail -1 || echo '')
    if [ -n \"\${LAUNCHER}\" ]; then
        adb shell am start -n \"\${LAUNCHER}\" || true
    else
        adb shell monkey -p \"\${PKG}\" -c android.intent.category.LAUNCHER 1 || true
    fi
"

echo ""
echo "✅ Done."
