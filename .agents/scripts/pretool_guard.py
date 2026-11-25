"""PreToolUse safety hook for Google Antigravity (.agents/hooks.json).

Reads Antigravity hook JSON payload on stdin and enforces safety gates on
`run_command` tool calls targeting Android devices via ADB:
- Denies known bootloop-inducing package removals and prohibited placebo commands
  (e.g., `cmd package compile -m everything -a`, `adb shell su`, raw `/system` writes).
- Forces explicit interactive user confirmation (`force_ask`) on mutating ADB
  commands or non-dry-run mutating optimizer scripts.
- Allows read-only checks and non-ADB commands immediately.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCKLIST_PATH = REPO_ROOT / "safety" / "hard_blocklist.json"

DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bcmd\s+package\s+compile\b.*\s-m\s+everything\b.*\s-a\b", re.IGNORECASE),
        "Prohibited command: `cmd package compile -m everything -a` bloats storage ~10x and degrades I/O. Use `bg-dexopt-job` or targeted `speed-profile`.",
    ),
    (
        re.compile(r"\bcmd\s+package\s+compile\b.*\s-m\s+speed\b.*\s-a\b", re.IGNORECASE),
        "Prohibited command: `cmd package compile -m speed -a` bloats storage across all apps. Use `bg-dexopt-job` or targeted `speed-profile`.",
    ),
    (
        re.compile(r"\badb\b.*\bshell\s+(?:su\b|mount\s+-o\s+rw|rm\s+-rf\s+/(?:system|vendor|product|data))", re.IGNORECASE),
        "Prohibited command: root shell (`su`), remounting `/system`, or destructive filesystem deletes are blocked.",
    ),
    (
        re.compile(r"\bpm\s+uninstall\b(?![^|;&]*--user\s+0)", re.IGNORECASE),
        "Unsafe uninstall: `pm uninstall` without `--user 0` is blocked. Only User 0 uninstalls (`pm uninstall -k --user 0 <pkg>`) are permitted.",
    ),
]

MUTATING_ADB_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpm\s+(?:uninstall|disable-user|enable|clear|trim-caches)\b", re.IGNORECASE), "Mutating PackageManager operation"),
    (re.compile(r"\b(?:cmd\s+package|pm)\s+install-existing\b", re.IGNORECASE), "Restoring package via PackageManager"),
    (re.compile(r"\b(?:cmd\s+package|pm)\s+(?:bg-dexopt-job|compile|art\s+(?:dexopt-packages|clear-app-profiles|cleanup))\b", re.IGNORECASE), "Running ART compilation/maintenance"),
    (re.compile(r"\bcmd\s+appops\s+set\b", re.IGNORECASE), "Modifying AppOps background permissions"),
    (re.compile(r"\bam\s+set-standby-bucket\b", re.IGNORECASE), "Modifying App Standby Bucket"),
    (re.compile(r"\bdevice_config\s+(?:put|delete)\b", re.IGNORECASE), "Modifying Android device_config flag"),
    (re.compile(r"\bsettings\s+(?:put|delete)\b", re.IGNORECASE), "Modifying Android system settings"),
    (re.compile(r"\bcmd\s+game\s+(?:mode|downscale|set|reset)\b", re.IGNORECASE), "Modifying Android Game Mode settings"),
    (re.compile(r"\bsm\s+fstrim\b", re.IGNORECASE), "Running storage trim (fstrim)"),
]

MUTATING_SCRIPT_PATTERN = re.compile(
    r"\b(?:debloat_packages|tune_performance|restore_package)\.(?:py|sh)\b",
    re.IGNORECASE,
)


def load_blocklist() -> dict[str, Any]:
    """Load offline hard blocklist JSON if present."""
    if not BLOCKLIST_PATH.exists():
        return {"exact_packages": {}, "protected_prefixes": []}
    try:
        return json.loads(BLOCKLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"exact_packages": {}, "protected_prefixes": []}


def extract_uninstall_targets(command: str) -> list[str]:
    """Extract package names passed to `pm uninstall` or `pm disable-user`."""
    pattern = re.compile(
        r"\bpm\s+(?:uninstall|disable-user)\b(?:\s+-[a-zA-Z]+|\s+--user\s+\d+)*\s+([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)",
        re.IGNORECASE,
    )
    return pattern.findall(command)


def evaluate_command(command: str) -> dict[str, str]:
    """Evaluate a shell CommandLine and return an Antigravity PreToolUse decision."""
    if not command or not command.strip():
        return {"decision": "allow"}

    # Fast path for commands unrelated to ADB or mutating optimizer scripts
    lowered = command.lower()
    if "adb" not in lowered and not MUTATING_SCRIPT_PATTERN.search(command):
        return {"decision": "allow"}

    for pattern, reason in DENY_PATTERNS:
        if pattern.search(command):
            return {"decision": "deny", "reason": reason}

    blocklist = load_blocklist()
    exact = blocklist.get("exact_packages", {})
    prefixes = blocklist.get("protected_prefixes", [])

    for pkg in extract_uninstall_targets(command):
        if pkg in exact:
            info = exact[pkg]
            detail = info.get("reason", "critical system/OEM component")
            return {
                "decision": "deny",
                "reason": f"Hard-blocked package `{pkg}`: {detail}. Removal can cause bootloops or break core device features.",
            }
        for prefix in prefixes:
            if pkg.startswith(prefix):
                return {
                    "decision": "deny",
                    "reason": f"Hard-blocked protected namespace `{pkg}` (matches `{prefix}`).",
                }

    if MUTATING_SCRIPT_PATTERN.search(command):
        if "--dry-run" in lowered or "--help" in lowered or "-h" in lowered.split():
            return {"decision": "allow"}
        return {
            "decision": "force_ask",
            "reason": "Mutating Android optimizer script detected. Confirm proposed changes before modifying the device.",
        }

    for pattern, label in MUTATING_ADB_PATTERNS:
        if pattern.search(command):
            return {
                "decision": "force_ask",
                "reason": f"{label} detected. Explicit user approval is required before mutating Android state.",
            }

    return {"decision": "allow"}


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return 0

    tool_call = payload.get("toolCall", {})
    if tool_call.get("name") != "run_command":
        print(json.dumps({"decision": "allow"}))
        return 0

    args = tool_call.get("args", {})
    command = str(args.get("CommandLine", ""))
    result = evaluate_command(command)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
