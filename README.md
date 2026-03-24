# docker_android_openclaw_batch_prompts

Emulator generating in Docker, install OpenClaw, open gateway, accept multiple prompts and output results.

## Overview

This project automates the following workflow inside a Docker container:

1. **Start an Android emulator** (Android 13 via `budtmo/docker-android`).
2. **Install the OpenClaw APK** onto the running emulator.
3. **Launch the OpenClaw gateway activity**.
4. **Send batch prompts** to the OpenClaw UI one by one via ADB.
5. **Collect responses** and write them to a JSON results file.

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker ≥ 24 | With `privileged` mode enabled (required by KVM/Android emulator) |
| Docker Compose v2 | `docker compose` plugin |
| OpenClaw APK | Place as `./openclaw.apk` in the repo root |
| KVM enabled | Required for hardware-accelerated Android emulator (`/dev/kvm`) |

## Quick Start

1. **Add your prompts** — edit `prompts/prompts.txt` (one prompt per line):

   ```
   What is the capital of France?
   Summarize the latest AI news.
   ```

2. **Place the OpenClaw APK** in the repo root:

   ```
   cp /path/to/openclaw.apk ./openclaw.apk
   ```

3. **Build and run**:

   ```bash
   docker compose up --build
   ```

4. **View results** — after the run completes, results are in `output/results.json`:

   ```json
   [
     {
       "index": 1,
       "prompt": "What is the capital of France?",
       "response": "Paris",
       "status": "success"
     }
   ]
   ```

## Configuration

All settings are controlled via environment variables (set in `docker-compose.yml` or passed with `-e`):

| Variable | Default | Description |
|---|---|---|
| `EMULATOR_DEVICE` | `Samsung Galaxy S10` | Android device profile |
| `OPENCLAW_APK` | `/app/openclaw.apk` | Path to APK inside the container |
| `PROMPTS_FILE` | `/app/prompts/prompts.txt` | Prompts input file (one per line) |
| `OUTPUT_FILE` | `/app/output/results.json` | JSON results output path |
| `PROMPT_DELAY` | `3` | Seconds to wait for a response after submitting a prompt |
| `BOOT_TIMEOUT` | `300` | Seconds to wait for the emulator to boot |
| `LAUNCH_TIMEOUT` | `30` | Seconds to wait for the gateway activity to become active |
| `PACKAGE` | `com.openclaw` | Android package name of OpenClaw |
| `INPUT_RES_ID` | `prompt_input` | Resource ID of the prompt EditText |
| `SUBMIT_RES_ID` | `submit_button` | Resource ID of the submit Button |
| `RESPONSE_RES_ID` | `response_text` | Resource ID of the response TextView |

## Project Structure

```
.
├── Dockerfile                  # Android emulator image definition
├── docker-compose.yml          # Container orchestration
├── requirements.txt            # Python dependencies
├── prompts/
│   └── example_prompts.txt     # Sample prompts file
├── scripts/
│   ├── run.sh                  # Main entrypoint
│   ├── start_emulator.sh       # Wait for emulator boot
│   ├── install_openclaw.sh     # Install APK and open gateway
│   └── batch_prompts.py        # Send prompts, collect responses
└── output/                     # Results written here (git-ignored)
```

## VNC Access

The container exposes a noVNC web interface on port **6080**.  
Open `http://localhost:6080` in your browser to watch the emulator.

## Notes

- The `output/` directory is git-ignored; mount it as a Docker volume to persist results.
- Adjust `INPUT_RES_ID`, `SUBMIT_RES_ID`, and `RESPONSE_RES_ID` to match the actual resource IDs in the OpenClaw APK.
- Run `adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml` from the host to inspect the UI hierarchy and find the correct resource IDs.
