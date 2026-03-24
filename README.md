# docker\_android\_openclaw\_batch\_prompts

End-to-end pipeline that:

1. Runs an **Android emulator** inside Docker (using [budtmo/docker-android](https://github.com/budtmo/docker-android)) with KVM acceleration
2. Installs the **OpenClaw** Android app inside the emulator via ADB
3. Exposes the **OpenClaw gateway** — including the OpenAI-compatible HTTP API
4. Reads prompts from a CSV file, submits each one to the gateway (restarting OpenClaw between prompts to clear memory), and writes all responses to a JSON file

---

## Repository layout

```
.
├── docker-compose.yml          # Android emulator + OpenClaw gateway services
├── config/
│   └── openclaw.json5          # Gateway config (enables HTTP chat-completions endpoint)
├── scripts/
│   ├── setup.sh                # One-shot setup (start containers → install APK → verify gateway)
│   ├── wait_for_emulator.sh    # Poll until the Android emulator is fully booted
│   └── install_openclaw.sh     # Download & ADB-install the OpenClaw APK
├── run_pipeline.py             # Main pipeline script (reads CSV → calls gateway → writes JSON)
├── requirements.txt            # Python dependencies
├── prompts.csv                 # 10 sample prompts
└── output.json                 # Sample output (one response object per prompt)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Ubuntu (host OS)** | KVM requires Linux; Windows/macOS users need a Linux VM |
| **KVM enabled** | `kvm-ok` must pass; use `--enable-kvm` or nested virtualisation on cloud VMs |
| **Docker ≥ 24** | <https://docs.docker.com/engine/install/ubuntu/> |
| **Docker Compose plugin** | Included with Docker Engine ≥ 23 |
| **Python ≥ 3.9** | Standard Ubuntu package: `sudo apt install python3 python3-pip` |
| **ADB (optional)** | Installed inside the Docker container; also useful on the host for debugging |

### Verify KVM

```bash
sudo apt install -y cpu-checker
kvm-ok
# Expected: "KVM acceleration can be used"
```

---

## Installation

### 1 — Clone the repository

```bash
git clone https://github.com/gongxuesusan/docker_android_openclaw_batch_prompts.git
cd docker_android_openclaw_batch_prompts
```

### 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3 — Obtain the OpenClaw APK

The OpenClaw Android APK installation instructions are published at:

> <https://gist.github.com/alisolanki/84422f89575970eac848f552af188816>

Follow the instructions in that gist to obtain `openclaw.apk` and place it in the **project root directory**.

Alternatively, set the `OPENCLAW_APK_URL` environment variable to a direct download URL before running setup:

```bash
export OPENCLAW_APK_URL="https://<url-to-openclaw.apk>"
```

### 4 — Set the gateway auth token (optional but recommended)

The default token is `changeme`. Override it with:

```bash
export OPENCLAW_GATEWAY_TOKEN="your-secret-token"
```

Or create a `.env` file in the project root:

```
OPENCLAW_GATEWAY_TOKEN=your-secret-token
```

---

## Running the pipeline

### Option A — One-shot setup + run

```bash
# Full setup: starts containers, waits for emulator, installs APK, verifies gateway
bash scripts/setup.sh

# Run the pipeline with the default prompts.csv
python run_pipeline.py
```

### Option B — Step by step

```bash
# 1. Start the Android emulator and the OpenClaw gateway
docker compose up -d

# 2. Wait for the emulator to finish booting (can take 3–5 minutes)
bash scripts/wait_for_emulator.sh

# 3. Install the OpenClaw APK
bash scripts/install_openclaw.sh

# 4. (Optional) Watch the emulator in a browser at http://localhost:6080

# 5. Run the pipeline
python run_pipeline.py \
    --prompts prompts.csv \
    --output  output.json \
    --token   "${OPENCLAW_GATEWAY_TOKEN:-changeme}"
```

### Pipeline options

```
python run_pipeline.py [OPTIONS]

  --prompts   CSV file with prompts             (default: prompts.csv)
  --output    Output JSON file                  (default: output.json)
  --gateway   Gateway base URL                  (default: http://localhost:18789)
  --token     Bearer auth token                 (default: $OPENCLAW_GATEWAY_TOKEN or "changeme")
  --model     OpenAI model field                (default: openclaw:main)
  --restart   Restart method between prompts    (docker | adb | none)  (default: docker)
  --container Gateway Docker container name     (default: openclaw-gateway)
  --timeout   Per-request timeout in seconds    (default: 120)
  --delay     Seconds to wait after restart     (default: 20)
```

#### Restart modes

| Mode | What happens between prompts |
|---|---|
| `docker` (default) | `docker restart openclaw-gateway` — restarts the Node.js gateway process, clearing all in-memory agent state |
| `adb` | `adb shell am force-stop <pkg>` + re-launch — restarts the Android app (use `--adb-pkg` to specify the package name) |
| `none` | No restart; prompts share the same agent session |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Ubuntu host (KVM enabled)                              │
│                                                         │
│  ┌──────────────────────────┐  ┌─────────────────────┐  │
│  │  android-emulator        │  │  openclaw-gateway   │  │
│  │  (budtmo/docker-android) │  │  (node:24-slim)     │  │
│  │                          │  │                     │  │
│  │  Android 11 emulator  ◄──┼──┤  openclaw gateway   │  │
│  │  OpenClaw APK installed  │  │  port 18789         │  │
│  │                          │  │                     │  │
│  │  ADB :5555               │  │  /v1/chat/          │  │
│  └──────────────────────────┘  │  completions        │  │
│                                └──────┬──────────────┘  │
│                                       │ HTTP            │
│  ┌────────────────────────┐           │                 │
│  │  run_pipeline.py       ├───────────┘                 │
│  │                        │                             │
│  │  reads prompts.csv     │  POST /v1/chat/completions  │
│  │  writes output.json    │  Authorization: Bearer ...  │
│  └────────────────────────┘                             │
└─────────────────────────────────────────────────────────┘
```

### How memory is cleared between prompts

Each time a prompt is processed, `run_pipeline.py` restarts the `openclaw-gateway` Docker container (or the Android app via ADB, depending on `--restart`). This forces a fresh gateway process — and therefore a new agent session — so no context from previous prompts leaks into subsequent ones.

---

## Input format — prompts.csv

The CSV file must have a header row. The script looks for a column named `prompt` (case-insensitive); if none is found it reads the first column.

```csv
prompt
What is the capital of France?
Explain deep learning in simple terms.
…
```

A ready-to-use `prompts.csv` with 10 sample prompts is included in the repository.

---

## Output format — output.json

```json
{
  "run_timestamp": "2026-03-24T02:00:00+00:00",
  "gateway_url": "http://localhost:18789",
  "model": "openclaw:main",
  "total_prompts": 10,
  "successful": 10,
  "failed": 0,
  "results": [
    {
      "index": 1,
      "prompt": "What is the capital of France?",
      "started_at": "2026-03-24T02:00:05+00:00",
      "status": "success",
      "error": null,
      "reply": "The capital of France is **Paris**.",
      "raw_response": { "...": "full OpenAI-format response object" }
    },
    ...
  ]
}
```

A sample `output.json` is included in the repository showing the expected shape.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `kvm-ok` fails | Enable nested virtualisation in your hypervisor / BIOS, or use a bare-metal Ubuntu machine |
| Emulator takes >5 min to boot | Increase `TIMEOUT` in `scripts/wait_for_emulator.sh`; check container logs: `docker logs android-emulator` |
| APK install fails | Make sure `openclaw.apk` is in the project root, or set `OPENCLAW_APK_URL` |
| Gateway not reachable at `:18789` | Check `docker logs openclaw-gateway`; ensure the container started: `docker compose ps` |
| 401 from gateway | Check that `OPENCLAW_GATEWAY_TOKEN` matches the token in `config/openclaw.json5` |
| Responses are empty / errors | Make sure OpenClaw is configured with a valid AI provider API key (see OpenClaw docs) |

---

## References

- [budtmo/docker-android](https://github.com/budtmo/docker-android) — Docker image for Android emulation
- [OpenClaw APK install gist](https://gist.github.com/alisolanki/84422f89575970eac848f552af188816) — Instructions for obtaining and installing the OpenClaw APK
- [OpenClaw OpenAI HTTP API docs](https://github.com/openclaw/openclaw/blob/ecc8fe5dc27eb9b8bc59910fdfbf008c676a3940/docs/gateway/openai-http-api.md) — Gateway HTTP endpoint reference
- [OpenClaw GitHub](https://github.com/openclaw/openclaw) — Main repository
