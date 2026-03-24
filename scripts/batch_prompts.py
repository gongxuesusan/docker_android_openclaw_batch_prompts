#!/usr/bin/env python3
"""batch_prompts.py

Read prompts from PROMPTS_FILE, send each one to the OpenClaw gateway running
inside the Android emulator via ADB, capture the on-screen response, and write
all results to OUTPUT_FILE as JSON.

Environment variables
---------------------
PROMPTS_FILE   Path to the plain-text file of prompts (one per line).
               Default: /app/prompts/prompts.txt
OUTPUT_FILE    Path for the JSON results output.
               Default: /app/output/results.json
PROMPT_DELAY   Seconds to wait after submitting a prompt before reading the
               response.  Default: 3
PACKAGE        Android package name of OpenClaw.
               Default: com.openclaw
INPUT_RES_ID   Resource ID of the prompt EditText (without package prefix).
               Default: prompt_input
SUBMIT_RES_ID  Resource ID of the submit Button (without package prefix).
               Default: submit_button
RESPONSE_RES_ID Resource ID of the TextView that shows the response.
               Default: response_text
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
PROMPTS_FILE = os.environ.get("PROMPTS_FILE", "/app/prompts/prompts.txt")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "/app/output/results.json")
PROMPT_DELAY = float(os.environ.get("PROMPT_DELAY", "3"))
PACKAGE = os.environ.get("PACKAGE", "com.openclaw")
INPUT_RES_ID = os.environ.get("INPUT_RES_ID", "prompt_input")
SUBMIT_RES_ID = os.environ.get("SUBMIT_RES_ID", "submit_button")
RESPONSE_RES_ID = os.environ.get("RESPONSE_RES_ID", "response_text")


# ── ADB helpers ──────────────────────────────────────────────────────────────

def _adb(*args: str, check: bool = True) -> str:
    """Run an adb command and return stdout as a string."""
    cmd = ["adb"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _adb_shell(*args: str, check: bool = True) -> str:
    return _adb("shell", *args, check=check)


def _get_center_coords(full_resource_id: str) -> tuple[str, str]:
    """Return the center x,y coordinates of a UI element as strings."""
    dump = _adb_shell("uiautomator", "dump", "/sdcard/ui.xml", check=False)
    xml_raw = _adb_shell("cat", "/sdcard/ui.xml", check=False)

    import xml.etree.ElementTree as ET  # noqa: PLC0415

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError as exc:
        raise RuntimeError(f"Could not parse UI dump: {exc}") from exc

    for node in root.iter("node"):
        if node.attrib.get("resource-id") == full_resource_id:
            bounds = node.attrib.get("bounds", "")
            # bounds format: [x1,y1][x2,y2]
            parts = bounds.replace("][", ",").strip("[]").split(",")
            if len(parts) == 4:
                cx = str((int(parts[0]) + int(parts[2])) // 2)
                cy = str((int(parts[1]) + int(parts[3])) // 2)
                return cx, cy
    raise RuntimeError(
        f"UI element '{full_resource_id}' not found in UI dump."
    )


def _set_text(resource_id: str, text: str) -> None:
    """Clear an EditText and type the given text into it."""
    cx, cy = _get_center_coords(f"{PACKAGE}:id/{resource_id}")
    _adb_shell("input", "tap", cx, cy)
    time.sleep(0.3)
    # Select all and delete existing text
    _adb_shell("input", "keyevent", "KEYCODE_CTRL_A")
    _adb_shell("input", "keyevent", "KEYCODE_DEL")
    # Type the new text (escape spaces and special chars via URL encoding)
    escaped = text.replace(" ", "%s").replace("'", "\\'")
    _adb_shell("input", "text", escaped)


def _get_text(resource_id: str) -> str:
    """Return the text content of a UI element."""
    full_id = f"{PACKAGE}:id/{resource_id}"
    _adb_shell("uiautomator", "dump", "/sdcard/ui.xml", check=False)
    xml_raw = _adb_shell("cat", "/sdcard/ui.xml", check=False)

    import xml.etree.ElementTree as ET  # noqa: PLC0415

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return ""

    for node in root.iter("node"):
        if node.attrib.get("resource-id") == full_id:
            return node.attrib.get("text", "")
    return ""


def _click_resource(resource_id: str) -> None:
    """Tap a UI element identified by its resource id."""
    cx, cy = _get_center_coords(f"{PACKAGE}:id/{resource_id}")
    _adb_shell("input", "tap", cx, cy)


# ── Core logic ───────────────────────────────────────────────────────────────

def send_prompt(prompt: str) -> str:
    """Type *prompt* into the input field, submit it, and return the response."""
    log.info("Sending prompt: %s", prompt[:80])
    _set_text(INPUT_RES_ID, prompt)
    time.sleep(0.5)
    _click_resource(SUBMIT_RES_ID)
    log.info("Waiting %.1f s for response...", PROMPT_DELAY)
    time.sleep(PROMPT_DELAY)
    response = _get_text(RESPONSE_RES_ID)
    log.info("Response: %s", response[:120])
    return response


def load_prompts(path: str) -> list[str]:
    """Load non-empty lines from *path* as prompts."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def save_results(results: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Results saved to %s", path)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Loading prompts from %s", PROMPTS_FILE)
    try:
        prompts = load_prompts(PROMPTS_FILE)
    except FileNotFoundError:
        log.error("Prompts file not found: %s", PROMPTS_FILE)
        sys.exit(1)

    if not prompts:
        log.warning("No prompts found in %s — nothing to do.", PROMPTS_FILE)
        return

    log.info("Processing %d prompt(s)...", len(prompts))
    results: list[dict] = []

    for idx, prompt in enumerate(prompts, start=1):
        log.info("[%d/%d] Processing prompt...", idx, len(prompts))
        try:
            response = send_prompt(prompt)
            status = "success"
        except Exception as exc:  # noqa: BLE001
            log.error("Error processing prompt %d: %s", idx, exc)
            response = ""
            status = f"error: {exc}"

        results.append(
            {
                "index": idx,
                "prompt": prompt,
                "response": response,
                "status": status,
            }
        )

    save_results(results, OUTPUT_FILE)
    log.info("All done — %d result(s) written.", len(results))


if __name__ == "__main__":
    main()
