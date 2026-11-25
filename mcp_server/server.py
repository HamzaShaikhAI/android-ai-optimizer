"""Zero-dependency scoped MCP stdio server for android-ai-optimizer.

Implements Model Context Protocol (JSON-RPC 2.0 over newline-delimited stdio)
using only the Python 3.10+ standard library. Exposes audited, injection-hardened
tools for the 5-stage Android optimization pipeline — with zero unrestricted
raw shell access.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import adb_common  # noqa: E402
import audit_device  # noqa: E402
import backup_packages  # noqa: E402
import benchmark_device  # noqa: E402
import check_packages  # noqa: E402
import debloat_packages  # noqa: E402
import restore_package  # noqa: E402
import sync_uad  # noqa: E402
import tune_performance  # noqa: E402

SERVER_INFO = {"name": "android-ai-optimizer", "version": "1.0.0"}
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")


def _tool_list_devices(args: dict[str, Any]) -> dict[str, Any]:
    devices = adb_common.list_devices()
    return {"bridge": adb_common.resolve_bridge_mode(), "devices": devices, "count": len(devices)}


def _tool_audit_device(args: dict[str, Any]) -> dict[str, Any]:
    adb_common.ensure_dirs()
    audit = audit_device.collect_audit(serial=args.get("serial"))
    ts = audit["audited_at"].replace(":", "").replace("-", "")
    latest_path = adb_common.LOGS_DIR / "latest_audit.json"
    timestamped_path = adb_common.LOGS_DIR / f"device_audit_{ts}.json"
    payload = json.dumps(audit, indent=2) + "\n"
    timestamped_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return {
        "summary_markdown": audit_device.format_summary_markdown(audit),
        "saved_to": str(latest_path.relative_to(REPO_ROOT)),
        "audit": audit,
    }


def _tool_backup_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    paths = backup_packages.capture_snapshot(serial=args.get("serial"))
    return {
        "status": "ok",
        "files": {k: str(v.relative_to(REPO_ROOT)) for k, v in paths.items()},
    }


def _tool_sync_uad(args: dict[str, Any]) -> dict[str, Any]:
    local_file = Path(args["local_file"]) if args.get("local_file") else None
    return sync_uad.sync_uad(
        force=bool(args.get("force", False)),
        local_file=local_file,
    )


def _tool_classify_packages(args: dict[str, Any]) -> dict[str, Any]:
    packages_file = args.get("packages_file")
    if packages_file:
        packages = check_packages.load_packages_from_backup(Path(packages_file))
    else:
        raw = adb_common.run_adb_shell(["pm", "list", "packages", "-e"], serial=args.get("serial"))
        packages = audit_device.parse_packages_output(raw)

    uad_db = check_packages.load_uad_database()
    blocklist = adb_common.load_blocklist()
    classified = check_packages.classify_packages(packages, uad_db, blocklist)

    tiers = args.get("tiers") or ["Recommended"]
    if "all" not in [t.lower() for t in tiers]:
        allowed = {t.lower() for t in tiers}
        filtered = [row for row in classified if row["tier"].lower() in allowed]
    else:
        filtered = classified

    return {
        "uad_database_loaded": bool(uad_db),
        "total_scanned": len(classified),
        "matched": len(filtered),
        "markdown_table": check_packages.render_markdown_table(filtered),
        "packages": filtered,
    }


def _tool_debloat_packages(args: dict[str, Any]) -> dict[str, Any]:
    packages = list(args.get("packages") or [])
    if not packages:
        raise ValueError("`packages` must be a non-empty list of package IDs.")
    dry_run = bool(args.get("dry_run", True))
    confirm = bool(args.get("confirm", False))
    if not dry_run and not confirm:
        raise ValueError("Mutating execution requires explicit `confirm: true` and `dry_run: false`.")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = debloat_packages.execute_debloat(
            packages=packages,
            serial=args.get("serial"),
            dry_run=dry_run,
            confirm=confirm,
            allow_advanced=bool(args.get("allow_advanced", False)),
            allow_unknown=bool(args.get("allow_unknown", False)),
            clear_data=bool(args.get("clear_data", False)),
        )
    return {"exit_code": rc, "dry_run": dry_run, "output": buf.getvalue()}


def _tool_restore_packages(args: dict[str, Any]) -> dict[str, Any]:
    packages = list(args.get("packages") or [])
    if args.get("restore_all"):
        packages.extend(restore_package.read_removed_packages())
    unique_targets = list(dict.fromkeys(packages))
    dry_run = bool(args.get("dry_run", False))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = restore_package.restore_packages(
            unique_targets,
            serial=args.get("serial"),
            dry_run=dry_run,
        )
    return {"exit_code": rc, "dry_run": dry_run, "packages": unique_targets, "output": buf.getvalue()}


def _tool_tune_performance(args: dict[str, Any]) -> dict[str, Any]:
    module = args.get("module")
    if module not in ("appops", "freezer", "art", "animations", "dns", "game"):
        raise ValueError("`module` must be one of: appops, freezer, art, animations, dns, game.")

    dry_run = bool(args.get("dry_run", True))
    confirm = bool(args.get("confirm", False))
    if not dry_run and not confirm:
        raise ValueError("Mutating tuning requires explicit `confirm: true` and `dry_run: false`.")
    if not dry_run and not adb_common.PACKAGES_BACKUP_PATH.exists():
        raise RuntimeError("Pre-flight snapshot logs/packages_backup.txt missing. Run `android_backup_snapshot` first.")

    serial = args.get("serial")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        if module == "appops":
            rc = tune_performance.run_appops_module(
                list(args.get("packages") or []),
                args.get("bucket"),
                bool(args.get("force_sensitive", False)),
                serial,
                dry_run,
                confirm,
            )
        elif module == "freezer":
            rc = tune_performance.run_freezer_module(serial, dry_run, confirm)
        elif module == "art":
            rc = tune_performance.run_art_module(
                list(args.get("packages") or []),
                bool(args.get("trim_caches", False)),
                bool(args.get("skip_fstrim", False)),
                bool(args.get("skip_bg_dexopt", False)),
                serial,
                dry_run,
                confirm,
            )
        elif module == "animations":
            rc = tune_performance.run_animations_module(
                float(args.get("scale", 0.5)),
                bool(args.get("disable_blurs", False)),
                serial,
                dry_run,
                confirm,
            )
        elif module == "dns":
            rc = tune_performance.run_dns_module(
                str(args.get("host", "adguard")),
                serial,
                dry_run,
                confirm,
            )
        else:
            rc = tune_performance.run_game_module(
                list(args.get("packages") or []),
                int(args.get("game_mode", 2)),
                args.get("downscale"),
                args.get("fps"),
                serial,
                dry_run,
                confirm,
            )
    return {"exit_code": rc, "module": module, "dry_run": dry_run, "output": buf.getvalue()}


def _tool_undo_tweaks(args: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(args.get("dry_run", True))
    limit = args.get("limit")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = restore_package.undo_recorded_tweaks(
            serial=args.get("serial"),
            dry_run=dry_run,
            limit=int(limit) if limit is not None else None,
        )
    return {"exit_code": rc, "dry_run": dry_run, "output": buf.getvalue()}


def _tool_benchmark_device(args: dict[str, Any]) -> dict[str, Any]:
    adb_common.ensure_dirs()
    phase = args.get("phase", "after")
    packages = list(args.get("packages") or [])
    serial = args.get("serial")

    if phase == "before":
        data = benchmark_device.collect_benchmark(packages, serial=serial)
        benchmark_device.BEFORE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return {"phase": "before", "saved_to": str(benchmark_device.BEFORE_PATH.relative_to(REPO_ROOT)), "data": data}

    if phase == "after":
        if not packages and benchmark_device.BEFORE_PATH.exists():
            prev = json.loads(benchmark_device.BEFORE_PATH.read_text(encoding="utf-8"))
            packages = [item["package"] for item in prev.get("cold_starts", [])]
        data = benchmark_device.collect_benchmark(packages, serial=serial)
        benchmark_device.AFTER_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        report = None
        if benchmark_device.BEFORE_PATH.exists():
            before = json.loads(benchmark_device.BEFORE_PATH.read_text(encoding="utf-8"))
            report = benchmark_device.render_comparison_report(before, data)
            benchmark_device.REPORT_PATH.write_text(report, encoding="utf-8")
        return {
            "phase": "after",
            "saved_to": str(benchmark_device.AFTER_PATH.relative_to(REPO_ROOT)),
            "report_markdown": report,
            "data": data,
        }

    if phase == "compare":
        if not benchmark_device.BEFORE_PATH.exists() or not benchmark_device.AFTER_PATH.exists():
            raise RuntimeError("Both logs/benchmark_before.json and logs/benchmark_after.json are required.")
        before = json.loads(benchmark_device.BEFORE_PATH.read_text(encoding="utf-8"))
        after = json.loads(benchmark_device.AFTER_PATH.read_text(encoding="utf-8"))
        report = benchmark_device.render_comparison_report(before, after)
        benchmark_device.REPORT_PATH.write_text(report, encoding="utf-8")
        return {"phase": "compare", "report_markdown": report}

    raise ValueError("`phase` must be one of: before, after, compare.")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "android_list_devices",
        "description": "List connected Android devices and authorization states via `adb devices -l` (read-only).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "android_audit_device",
        "description": "Stage 1: Run read-only diagnostic audit (OEM profile, RAM, 24h procstats, wakeups, storage, Freezer, ART state).",
        "inputSchema": {
            "type": "object",
            "properties": {"serial": {"type": "string", "description": "Optional ADB device serial."}},
            "additionalProperties": False,
        },
    },
    {
        "name": "android_backup_snapshot",
        "description": "Stage 2: Capture pre-flight reversible snapshot of packages, settings, and rollback ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {"serial": {"type": "string", "description": "Optional ADB device serial."}},
            "additionalProperties": False,
        },
    },
    {
        "name": "android_sync_uad",
        "description": "Download and cache UAD-NG uad_lists.json locally into cache/uad_lists.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "default": False},
                "local_file": {"type": "string", "description": "Optional local path to uad_lists.json."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "android_classify_packages",
        "description": "Stage 3 (read-only): Cross-reference installed or backed-up packages against UAD-NG and safety/hard_blocklist.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "serial": {"type": "string"},
                "packages_file": {"type": "string"},
                "tiers": {"type": "array", "items": {"type": "string"}, "default": ["Recommended"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "android_debloat_packages",
        "description": "Stage 3: Validate and uninstall approved packages for User 0. Defaults to dry_run=true; requires confirm=true and dry_run=false to execute.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "serial": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm": {"type": "boolean", "default": False},
                "allow_advanced": {"type": "boolean", "default": False},
                "allow_unknown": {"type": "boolean", "default": False},
                "clear_data": {"type": "boolean", "default": False},
            },
            "required": ["packages"],
            "additionalProperties": False,
        },
    },
    {
        "name": "android_restore_packages",
        "description": "1-click restore for User-0 uninstalled packages via `cmd package install-existing`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
                "restore_all": {"type": "boolean", "default": False},
                "serial": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "android_tune_performance",
        "description": "Stage 4: Run verified non-root modules (appops, freezer, art, animations, dns, game). Defaults to dry_run=true; requires confirm=true and dry_run=false.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "enum": ["appops", "freezer", "art", "animations", "dns", "game"]},
                "packages": {"type": "array", "items": {"type": "string"}},
                "bucket": {"type": "string", "enum": ["rare", "restricted"]},
                "force_sensitive": {"type": "boolean", "default": False},
                "trim_caches": {"type": "boolean", "default": False},
                "skip_fstrim": {"type": "boolean", "default": False},
                "skip_bg_dexopt": {"type": "boolean", "default": False},
                "scale": {"type": "number", "default": 0.5},
                "disable_blurs": {"type": "boolean", "default": False},
                "host": {"type": "string", "default": "adguard"},
                "game_mode": {"type": "integer", "enum": [1, 2, 3], "default": 2},
                "downscale": {"type": "number"},
                "fps": {"type": "integer"},
                "serial": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm": {"type": "boolean", "default": False},
            },
            "required": ["module"],
            "additionalProperties": False,
        },
    },
    {
        "name": "android_undo_tweaks",
        "description": "Revert recorded settings, AppOps, DNS, freezer, game mode, or package actions from logs/rollback_log.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "serial": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "android_benchmark_device",
        "description": "Stage 5: Measure before/after RAM, background services, and app cold-start TotalTime (ms), generating logs/optimization_report.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "enum": ["before", "after", "compare"], "default": "after"},
                "packages": {"type": "array", "items": {"type": "string"}},
                "serial": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]

HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "android_list_devices": _tool_list_devices,
    "android_audit_device": _tool_audit_device,
    "android_backup_snapshot": _tool_backup_snapshot,
    "android_sync_uad": _tool_sync_uad,
    "android_classify_packages": _tool_classify_packages,
    "android_debloat_packages": _tool_debloat_packages,
    "android_restore_packages": _tool_restore_packages,
    "android_tune_performance": _tool_tune_performance,
    "android_undo_tweaks": _tool_undo_tweaks,
    "android_benchmark_device": _tool_benchmark_device,
}


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 request and return a response dict (or None for notifications)."""
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized" or (req_id is None and str(method).startswith("notifications/")):
        return None

    if method == "initialize":
        requested_ver = str(params.get("protocolVersion") or SUPPORTED_PROTOCOL_VERSIONS[0])
        chosen = requested_ver if requested_ver in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": chosen,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in HANDLERS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        try:
            data = HANDLERS[name](arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"ERROR: {exc}"}],
                    "isError": True,
                },
            }

    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            req = json.loads(text)
        except json.JSONDecodeError as exc:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
