#!/usr/bin/env python3
"""
run_pipeline.py
───────────────
End-to-end pipeline:

  1. Read prompts from a CSV file (one prompt per row, column "prompt").
  2. For each prompt:
       a. Restart OpenClaw (Android app + gateway) to clear in-memory context.
       b. Wait for the gateway to be ready.
       c. POST the prompt to the OpenAI-compatible /v1/chat/completions endpoint.
       d. Collect the response.
  3. Write all results to an output JSON file.

Usage
-----
  python run_pipeline.py [OPTIONS]

Options
-------
  --prompts   Path to input CSV file           (default: prompts.csv)
  --output    Path to output JSON file         (default: output.json)
  --gateway   Gateway base URL                 (default: http://localhost:18789)
  --token     Bearer token for authentication  (default: $OPENCLAW_GATEWAY_TOKEN or "changeme")
  --model     OpenAI model field value         (default: openclaw:main)
  --restart   Restart method: "docker" | "adb" | "none"  (default: docker)
  --container Gateway Docker container name    (default: openclaw-gateway)
  --adb-pkg   Android package name for ADB restart
  --timeout   Per-request timeout in seconds   (default: 120)
  --delay     Seconds to wait after restart    (default: 20)
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# ── Helpers ───────────────────────────────────────────────────────────────────


def wait_for_gateway(gateway_url: str, token: str, timeout: int = 60, interval: int = 5) -> None:
    """Block until the gateway returns a non-5xx response or timeout expires."""
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            resp = requests.post(
                f"{gateway_url}/v1/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                json={"model": "openclaw:main", "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            if resp.status_code < 500:
                return  # gateway is up (even a 401/400 means it is listening)
        except requests.exceptions.ConnectionError as exc:
            last_err = str(exc)
        time.sleep(interval)
    raise TimeoutError(
        f"Gateway at {gateway_url} did not become ready within {timeout}s. "
        f"Last error: {last_err}"
    )


def restart_via_docker(container: str, gateway_url: str, token: str, delay: int) -> None:
    """Restart the openclaw-gateway Docker container."""
    print(f"    🔄 Restarting Docker container '{container}' …")
    try:
        subprocess.run(
            ["docker", "restart", container],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"    ⚠️  docker restart failed: {exc.stderr.strip()}", file=sys.stderr)
    print(f"    ⏳ Waiting {delay}s for container to come back …")
    time.sleep(delay)
    wait_for_gateway(gateway_url, token, timeout=120)


def restart_via_adb(package: str, container: str, gateway_url: str, token: str, delay: int) -> None:
    """Force-stop and re-launch the OpenClaw Android app via ADB, then wait for the gateway."""
    if not package:
        print("    ⚠️  --adb-pkg not set; skipping ADB restart.", file=sys.stderr)
        return

    print(f"    🔄 Restarting Android app '{package}' via ADB …")
    try:
        # Force-stop
        subprocess.run(
            ["docker", "exec", container, "adb", "shell", "am", "force-stop", package],
            check=True,
            capture_output=True,
            text=True,
        )
        time.sleep(2)
        # Re-launch
        subprocess.run(
            [
                "docker", "exec", container,
                "adb", "shell", "monkey",
                "-p", package, "-c", "android.intent.category.LAUNCHER", "1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"    ⚠️  ADB restart failed: {exc.stderr.strip()}", file=sys.stderr)

    print(f"    ⏳ Waiting {delay}s for app to initialise …")
    time.sleep(delay)
    wait_for_gateway(gateway_url, token, timeout=120)


def call_gateway(gateway_url: str, token: str, prompt: str, model: str, timeout: int) -> dict:
    """POST a single prompt to the OpenClaw gateway and return the JSON response."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        f"{gateway_url}/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a batch of prompts through the OpenClaw gateway."
    )
    parser.add_argument("--prompts",   default="prompts.csv",                        help="Input CSV file path (default: prompts.csv)")
    parser.add_argument("--output",    default="output.json",                        help="Output JSON file path (default: output.json)")
    parser.add_argument("--gateway",   default="http://localhost:18789",              help="Gateway base URL")
    parser.add_argument("--token",     default=os.environ.get("OPENCLAW_GATEWAY_TOKEN", "changeme"), help="Bearer token")
    parser.add_argument("--model",     default="openclaw:main",                      help="OpenAI model field (default: openclaw:main)")
    parser.add_argument("--restart",   default="docker",  choices=["docker", "adb", "none"], help="Restart method between prompts")
    parser.add_argument("--container", default="openclaw-gateway",                   help="Gateway Docker container name")
    parser.add_argument("--adb-container", default="android-emulator",               help="Android emulator Docker container name (for ADB restart)")
    parser.add_argument("--adb-pkg",   default="",                                   help="Android package name for ADB restart")
    parser.add_argument("--timeout",   type=int, default=120,                        help="Per-request timeout in seconds")
    parser.add_argument("--delay",     type=int, default=20,                         help="Seconds to wait after restart before sending request")
    args = parser.parse_args()

    # ── Read prompts ──────────────────────────────────────────────────────────

    prompts_path = Path(args.prompts)
    if not prompts_path.exists():
        print(f"❌ Prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(1)

    prompts = []
    with prompts_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Accept a column named "prompt" (case-insensitive); fall back to the
        # first column if the header is absent or differently named.
        header = [c.lower() for c in (reader.fieldnames or [])]
        prompt_col = None
        if "prompt" in header:
            prompt_col = reader.fieldnames[header.index("prompt")]
        for row in reader:
            text = (row.get(prompt_col) or next(iter(row.values()), "")).strip()
            if text:
                prompts.append(text)

    if not prompts:
        print("❌ No prompts found in CSV file.", file=sys.stderr)
        sys.exit(1)

    print(f"📋 Loaded {len(prompts)} prompt(s) from '{prompts_path}'.")

    # ── Process prompts ───────────────────────────────────────────────────────

    results = []
    run_timestamp = datetime.now(timezone.utc).isoformat()

    for idx, prompt in enumerate(prompts, start=1):
        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(prompts)}] Prompt: {prompt[:80]}{'…' if len(prompt) > 80 else ''}")

        # Restart OpenClaw to clear context
        if args.restart == "docker":
            restart_via_docker(args.container, args.gateway, args.token, args.delay)
        elif args.restart == "adb":
            restart_via_adb(args.adb_pkg, args.adb_container, args.gateway, args.token, args.delay)
        else:
            print("    ⏭  Skipping restart (--restart=none).")

        # Send prompt to gateway
        started_at = datetime.now(timezone.utc).isoformat()
        print(f"    📤 Sending to gateway …")
        try:
            response_json = call_gateway(
                args.gateway, args.token, prompt, args.model, args.timeout
            )
            # Extract the assistant reply for convenience
            reply = ""
            choices = response_json.get("choices", [])
            if choices:
                reply = choices[0].get("message", {}).get("content", "")
            status = "success"
            error = None
            print(f"    ✅ Response received ({len(reply)} chars).")
        except Exception as exc:
            response_json = {}
            reply = ""
            status = "error"
            error = str(exc)
            print(f"    ❌ Error: {error}", file=sys.stderr)

        results.append(
            {
                "index": idx,
                "prompt": prompt,
                "started_at": started_at,
                "status": status,
                "error": error,
                "reply": reply,
                "raw_response": response_json,
            }
        )

    # ── Write output ──────────────────────────────────────────────────────────

    output = {
        "run_timestamp": run_timestamp,
        "gateway_url": args.gateway,
        "model": args.model,
        "total_prompts": len(prompts),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"\n{'═' * 60}")
    print(f"✅ Pipeline complete.")
    print(f"   Prompts processed : {len(prompts)}")
    print(f"   Successful        : {output['successful']}")
    print(f"   Failed            : {output['failed']}")
    print(f"   Output written to : {output_path.resolve()}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
