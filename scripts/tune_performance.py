"""Stage 4: Modular non-root Android performance tuning (Modules A-F) with AOSP version checks & rollback."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    PACKAGES_BACKUP_PATH,
    AdbDeviceError,
    append_rollback_action,
    ensure_dirs,
    is_never_throttle,
    load_blocklist,
    run_adb_shell,
    validate_package_name,
)

DNS_PRESETS = {
    "adguard": "dns.adguard-dns.com",
    "cloudflare": "one.one.one.one",
    "quad9": "dns.quad9.net",
}
HOSTNAME_RE = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")


def get_device_sdk(serial: str | None = None) -> int:
    """Return numeric Android SDK level (or 0 if unavailable)."""
    raw = run_adb_shell(["getprop", "ro.build.version.sdk"], serial=serial, check=False).strip()
    return int(raw) if raw.isdigit() else 0


def parse_appops_mode(raw: str) -> str:
    """Extract AppOps mode (`default`, `allow`, `ignore`, `deny`) from `cmd appops get` output."""
    low = raw.lower()
    if not low or "no operations" in low:
        return "default"
    for mode in ("ignore", "deny", "allow", "default", "foreground"):
        if f": {mode}" in low or low.endswith(mode):
            return mode
    return "default"


def _require_confirmation(dry_run: bool, confirm: bool, summary: str) -> bool:
    print(summary)
    if dry_run:
        print("[DRY-RUN] No changes were applied.")
        return False
    if confirm:
        return True
    reply = input("Type 'yes' to apply these changes: ").strip().lower()
    return reply == "yes"


def run_appops_module(
    packages: list[str],
    bucket: str | None,
    force_sensitive: bool,
    serial: str | None,
    dry_run: bool,
    confirm: bool,
) -> int:
    """Module A: Throttle background execution via AppOps & optional Standby Buckets."""
    sdk = get_device_sdk(serial)
    if sdk and sdk < 28:
        print(f"ERROR: Module A requires Android 9+ (SDK >= 28); device reports SDK {sdk}.", file=sys.stderr)
        return 1

    blocklist = load_blocklist()
    validated: list[str] = []
    for raw in packages:
        pkg = validate_package_name(raw)
        sensitive, kw = is_never_throttle(pkg, blocklist)
        if sensitive and not force_sensitive:
            print(
                f"SKIPPED `{pkg}`: matched sensitive keyword `{kw}` (alarms/messaging/UPI/banking/accessibility). "
                "Pass `--force-sensitive` only if you are sure.",
                file=sys.stderr,
            )
            continue
        validated.append(pkg)

    if not validated:
        print("No eligible packages to throttle.", file=sys.stderr)
        return 1

    effective_bucket = bucket
    if effective_bucket == "restricted" and sdk and sdk < 30:
        print(f"NOTE: `restricted` standby bucket requires Android 11+ (SDK 30+); using `rare` on SDK {sdk}.")
        effective_bucket = "rare"

    preview = [f"Module A (AppOps): targeting {len(validated)} package(s): {', '.join(validated)}"]
    if effective_bucket:
        preview.append(f"  - Standby bucket: `{effective_bucket}`")
    if not _require_confirmation(dry_run, confirm, "\n".join(preview)):
        return 0 if dry_run else 1

    for pkg in validated:
        prior_any = parse_appops_mode(
            run_adb_shell(["cmd", "appops", "get", pkg, "RUN_ANY_IN_BACKGROUND"], serial=serial, check=False)
        )
        prior_in_bg = parse_appops_mode(
            run_adb_shell(["cmd", "appops", "get", pkg, "RUN_IN_BACKGROUND"], serial=serial, check=False)
        )
        prior_bucket = run_adb_shell(["am", "get-standby-bucket", pkg], serial=serial, check=False).strip()

        run_adb_shell(["cmd", "appops", "set", pkg, "RUN_ANY_IN_BACKGROUND", "ignore"], serial=serial)
        run_adb_shell(["cmd", "appops", "set", pkg, "RUN_IN_BACKGROUND", "ignore"], serial=serial)

        append_rollback_action(
            {
                "type": "appops_run_any_in_bg",
                "package": pkg,
                "previous_value": prior_any,
                "undo_args": ["cmd", "appops", "set", pkg, "RUN_ANY_IN_BACKGROUND", prior_any],
                "undo_command": f"adb shell cmd appops set {pkg} RUN_ANY_IN_BACKGROUND {prior_any}",
            }
        )
        append_rollback_action(
            {
                "type": "appops_run_in_bg",
                "package": pkg,
                "previous_value": prior_in_bg,
                "undo_args": ["cmd", "appops", "set", pkg, "RUN_IN_BACKGROUND", prior_in_bg],
                "undo_command": f"adb shell cmd appops set {pkg} RUN_IN_BACKGROUND {prior_in_bg}",
            }
        )
        if effective_bucket:
            run_adb_shell(["am", "set-standby-bucket", pkg, effective_bucket], serial=serial)
            restore_bucket = (
                prior_bucket
                if prior_bucket.isdigit()
                or prior_bucket in ("active", "working_set", "frequent", "rare", "restricted")
                else "active"
            )
            append_rollback_action(
                {
                    "type": "standby_bucket",
                    "package": pkg,
                    "previous_value": prior_bucket,
                    "undo_args": ["am", "set-standby-bucket", pkg, restore_bucket],
                }
            )
        print(
            f"THROTTLED `{pkg}` (AppOps background ignored"
            + (f", bucket={effective_bucket}" if effective_bucket else "")
            + ")."
        )
    return 0


def run_freezer_module(serial: str | None, dry_run: bool, confirm: bool) -> int:
    """Module B: Verify cgroup v2 freezer support and persist Cached Apps Freezer."""
    sdk = get_device_sdk(serial)
    if sdk and sdk < 30:
        print(f"ERROR: Cached Apps Freezer requires Android 11+ (SDK >= 30); device reports SDK {sdk}.", file=sys.stderr)
        return 1

    controllers = run_adb_shell(["cat", "/sys/fs/cgroup/cgroup.controllers"], serial=serial, check=False).strip()
    if "freezer" not in controllers.split():
        print(
            f"ERROR: Kernel does not advertise `freezer` in `/sys/fs/cgroup/cgroup.controllers` (got: {controllers!r}).",
            file=sys.stderr,
        )
        return 1

    prior_flag = run_adb_shell(
        ["device_config", "get", "activity_manager_native_boot", "use_freezer"],
        serial=serial,
        check=False,
    ).strip()
    prior_setting = run_adb_shell(
        ["settings", "get", "global", "cached_apps_freezer"],
        serial=serial,
        check=False,
    ).strip()

    if not _require_confirmation(
        dry_run,
        confirm,
        "Module B (Cached Apps Freezer): kernel supports cgroup v2 freezer.\n"
        f"  - `settings put global cached_apps_freezer enabled` (current: {prior_setting or 'unset'})\n"
        f"  - `device_config put activity_manager_native_boot use_freezer true` (current: {prior_flag or 'unset'})\n"
        "  - Takes effect after device reboot.",
    ):
        return 0 if dry_run else 1

    run_adb_shell(["settings", "put", "global", "cached_apps_freezer", "enabled"], serial=serial)
    run_adb_shell(["device_config", "put", "activity_manager_native_boot", "use_freezer", "true"], serial=serial)

    append_rollback_action(
        {
            "type": "setting_cached_apps_freezer",
            "previous_value": prior_setting,
            "undo_args": ["settings", "put", "global", "cached_apps_freezer", prior_setting]
            if prior_setting and prior_setting != "null"
            else ["settings", "put", "global", "cached_apps_freezer", "device_default"],
        }
    )
    append_rollback_action(
        {
            "type": "device_config_freezer",
            "previous_value": prior_flag,
            "undo_args": ["device_config", "put", "activity_manager_native_boot", "use_freezer", prior_flag]
            if prior_flag and prior_flag != "null"
            else ["device_config", "delete", "activity_manager_native_boot", "use_freezer"],
        }
    )
    print("ENABLED Cached Apps Freezer (`cached_apps_freezer=enabled`, `use_freezer=true`). Reboot the device to activate.")
    return 0


def run_art_module(
    compile_packages: list[str],
    trim_caches: bool,
    skip_fstrim: bool,
    skip_bg_dexopt: bool,
    serial: str | None,
    dry_run: bool,
    confirm: bool,
) -> int:
    """Module C: Android-version-aware ART profile compilation + optional cache trim & graceful fstrim."""
    sdk = get_device_sdk(serial)
    validated = [validate_package_name(p) for p in compile_packages]

    steps: list[str] = []
    if trim_caches:
        steps.append("- `pm trim-caches 100G` (explicitly requested via --trim-caches)")
    if not skip_bg_dexopt:
        if sdk >= 34:
            steps.append("- `pm art dexopt-packages -r bg-dexopt` (Android 14+ ART Service)")
        else:
            steps.append("- `cmd package bg-dexopt-job`")
    for pkg in validated:
        steps.append(f"- `cmd package compile -m speed-profile -f {pkg}`")
    if not skip_fstrim:
        steps.append("- `sm fstrim` (best-effort; skipped gracefully if OEM restricts shell UID)")

    if not _require_confirmation(dry_run, confirm, "Module C (ART & Storage Maintenance):\n" + "\n".join(steps)):
        return 0 if dry_run else 1

    if trim_caches:
        print("Running `pm trim-caches 100G`...", flush=True)
        print(run_adb_shell(["pm", "trim-caches", "100G"], serial=serial, check=False).strip() or "ok", flush=True)

    if not skip_bg_dexopt:
        if sdk >= 34:
            print("Running Android 14+ ART Service (`pm art dexopt-packages -r bg-dexopt`)...", flush=True)
            try:
                art_out = run_adb_shell(
                    ["pm", "art", "dexopt-packages", "-r", "bg-dexopt"],
                    serial=serial,
                    check=False,
                    timeout=600,
                ).strip()
                if "unknown command" in art_out.lower() or "error" in art_out.lower():
                    art_out = run_adb_shell(["cmd", "package", "bg-dexopt-job"], serial=serial, check=False, timeout=600).strip()
                print(art_out or "ok", flush=True)
            except subprocess.TimeoutExpired:
                print(
                    "NOTE: `pm art dexopt-packages -r bg-dexopt` timed out after 600s (partial sweep completed; "
                    "continuing with targeted `speed-profile` compilation).",
                    flush=True,
                )
        else:
            print("Running `cmd package bg-dexopt-job` (may take 1-5 minutes)...", flush=True)
            try:
                print(run_adb_shell(["cmd", "package", "bg-dexopt-job"], serial=serial, check=False, timeout=600).strip() or "ok", flush=True)
            except subprocess.TimeoutExpired:
                print(
                    "NOTE: `cmd package bg-dexopt-job` timed out after 600s (partial sweep completed; "
                    "continuing with targeted `speed-profile` compilation).",
                    flush=True,
                )

    for pkg in validated:
        print(f"Compiling `{pkg}` with `speed-profile`...", flush=True)
        out = run_adb_shell(
            ["cmd", "package", "compile", "-m", "speed-profile", "-f", pkg],
            serial=serial,
            check=False,
            timeout=180,
        )
        print(out.strip() or "ok", flush=True)

    if not skip_fstrim:
        print("Running `sm fstrim` (best-effort)...", flush=True)
        fstrim_out = run_adb_shell(["sm", "fstrim"], serial=serial, check=False, timeout=180).strip()
        if any(err in fstrim_out.lower() for err in ("securityexception", "permission denial", "permission denied")):
            print(
                f"NOTE: `sm fstrim` requires system/root privileges on this build ({fstrim_out}). "
                "Android automatically schedules fstrim during idle charging."
            )
        else:
            print(fstrim_out or "ok")
    return 0


def run_animations_module(
    scale: float,
    disable_blurs: bool,
    serial: str | None,
    dry_run: bool,
    confirm: bool,
) -> int:
    """Module D: Set window/transition/animator scales and optional disable_window_blurs."""
    if not (0.0 <= scale <= 2.0):
        raise ValueError("Animation scale must be between 0.0 and 2.0.")
    keys = ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"]
    priors = {k: run_adb_shell(["settings", "get", "global", k], serial=serial, check=False).strip() for k in keys}
    prior_blurs = (
        run_adb_shell(["settings", "get", "global", "disable_window_blurs"], serial=serial, check=False).strip()
        if disable_blurs
        else None
    )

    msg = f"Module D (UI Animations): set {', '.join(keys)} to `{scale}` (current: {priors})."
    if disable_blurs:
        msg += f"\n  - Also set `disable_window_blurs` to `1` (current: `{prior_blurs or 'unset'}`)."
    if not _require_confirmation(dry_run, confirm, msg):
        return 0 if dry_run else 1

    for key in keys:
        run_adb_shell(["settings", "put", "global", key, str(scale)], serial=serial)
        prior = priors[key]
        undo_args = ["settings", "put", "global", key, prior] if prior and prior != "null" else ["settings", "delete", "global", key]
        append_rollback_action(
            {
                "type": "setting_global",
                "key": key,
                "previous_value": prior,
                "new_value": str(scale),
                "undo_args": undo_args,
            }
        )
    if disable_blurs:
        run_adb_shell(["settings", "put", "global", "disable_window_blurs", "1"], serial=serial)
        undo_blur_args = (
            ["settings", "put", "global", "disable_window_blurs", prior_blurs]
            if prior_blurs and prior_blurs != "null"
            else ["settings", "delete", "global", "disable_window_blurs"]
        )
        append_rollback_action(
            {
                "type": "setting_global",
                "key": "disable_window_blurs",
                "previous_value": prior_blurs,
                "new_value": "1",
                "undo_args": undo_blur_args,
            }
        )
    print(f"Animation scales updated to `{scale}`" + (" and `disable_window_blurs=1`" if disable_blurs else "") + ".")
    return 0


def run_dns_module(host: str, serial: str | None, dry_run: bool, confirm: bool) -> int:
    """Module E: Configure Private DNS (DNS-over-TLS) for system-wide ad/tracker blocking."""
    sdk = get_device_sdk(serial)
    if sdk and sdk < 28:
        print(f"ERROR: Private DNS requires Android 9+ (SDK >= 28); device reports SDK {sdk}.", file=sys.stderr)
        return 1

    resolved_host = DNS_PRESETS.get(host.lower(), host.strip())
    if not HOSTNAME_RE.match(resolved_host):
        raise ValueError(f"Invalid Private DNS hostname: {host!r}")

    prior_mode = run_adb_shell(["settings", "get", "global", "private_dns_mode"], serial=serial, check=False).strip()
    prior_spec = run_adb_shell(["settings", "get", "global", "private_dns_specifier"], serial=serial, check=False).strip()

    if not _require_confirmation(
        dry_run,
        confirm,
        f"Module E (Private DNS): set `private_dns_mode=hostname`, `private_dns_specifier={resolved_host}` "
        f"(current: mode={prior_mode}, specifier={prior_spec}).",
    ):
        return 0 if dry_run else 1

    run_adb_shell(["settings", "put", "global", "private_dns_mode", "hostname"], serial=serial)
    run_adb_shell(["settings", "put", "global", "private_dns_specifier", resolved_host], serial=serial)

    append_rollback_action(
        {
            "type": "private_dns_mode",
            "previous_value": prior_mode,
            "undo_args": ["settings", "put", "global", "private_dns_mode", prior_mode]
            if prior_mode and prior_mode != "null"
            else ["settings", "put", "global", "private_dns_mode", "opportunistic"],
        }
    )
    append_rollback_action(
        {
            "type": "private_dns_specifier",
            "previous_value": prior_spec,
            "undo_args": ["settings", "put", "global", "private_dns_specifier", prior_spec]
            if prior_spec and prior_spec != "null"
            else ["settings", "delete", "global", "private_dns_specifier"],
        }
    )
    print(f"Private DNS configured to `{resolved_host}`.")
    return 0


def run_game_module(
    packages: list[str],
    mode: int,
    downscale: float | None,
    fps: int | None,
    serial: str | None,
    dry_run: bool,
    confirm: bool,
) -> int:
    """Module F: Android 12+ Game Mode performance and Android 13+ `cmd game set` interventions."""
    sdk = get_device_sdk(serial)
    if sdk and sdk < 31:
        print(f"ERROR: Module F requires Android 12+ (SDK >= 31); device reports SDK {sdk}.", file=sys.stderr)
        return 1

    validated = [validate_package_name(p) for p in packages]
    if downscale is not None and not (0.3 <= downscale <= 0.9):
        raise ValueError("Game downscale factor must be between 0.3 and 0.9.")
    if fps is not None and fps not in (30, 45, 60, 90, 120):
        raise ValueError("Game FPS cap must be one of 30, 45, 60, 90, or 120.")

    mode_name = {1: "standard", 2: "performance", 3: "battery"}[mode]
    summary = (
        f"Module F (Game Mode, SDK {sdk or 'unknown'}): mode={mode_name}"
        + (f", downscale={downscale}" if downscale is not None else "")
        + (f", fps={fps}" if fps is not None else "")
        + f" on {', '.join(validated)}"
    )
    if not _require_confirmation(dry_run, confirm, summary):
        return 0 if dry_run else 1

    for pkg in validated:
        if sdk >= 33:
            if downscale is not None or fps is not None:
                cmd_args = ["cmd", "game", "set"]
                if downscale is not None:
                    cmd_args.extend(["--downscale", str(downscale)])
                if fps is not None:
                    cmd_args.extend(["--fps", str(fps)])
                cmd_args.append(pkg)
                run_adb_shell(cmd_args, serial=serial)
                run_adb_shell(["cmd", "game", "mode", "custom", pkg], serial=serial, check=False)
                append_rollback_action(
                    {
                        "type": "game_intervention",
                        "package": pkg,
                        "undo_args": ["cmd", "game", "reset", pkg],
                    }
                )
            else:
                run_adb_shell(["cmd", "game", "mode", mode_name, pkg], serial=serial)
                append_rollback_action(
                    {
                        "type": "game_mode",
                        "package": pkg,
                        "undo_args": ["cmd", "game", "mode", "standard", pkg],
                    }
                )
        else:
            run_adb_shell(["cmd", "game", "mode", str(mode), pkg], serial=serial)
            append_rollback_action(
                {
                    "type": "game_mode",
                    "package": pkg,
                    "undo_args": ["cmd", "game", "mode", "1", pkg],
                }
            )
            if downscale is not None:
                run_adb_shell(["cmd", "game", "downscale", str(downscale), pkg], serial=serial)
                append_rollback_action(
                    {
                        "type": "game_downscale",
                        "package": pkg,
                        "undo_args": ["cmd", "game", "downscale", "disable", pkg],
                    }
                )
        print(f"APPLIED Game Mode `{mode_name}` to `{pkg}` (force-close and relaunch game to apply).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4: Non-root Android performance tuning modules (A-F).")
    parser.add_argument("--module", required=True, choices=("appops", "freezer", "art", "animations", "dns", "game"))
    parser.add_argument("--serial", help="Target ADB device serial.")
    parser.add_argument("--packages", nargs="*", default=[], help="Target package IDs (for appops, art, game).")
    parser.add_argument("--bucket", choices=("rare", "restricted"), help="Optional standby bucket for Module A.")
    parser.add_argument("--force-sensitive", action="store_true", help="Override banking/messaging/alarm throttle guard.")
    parser.add_argument("--trim-caches", action="store_true", help="Opt-in `pm trim-caches 100G` during Module C (only recommended when storage is low).")
    parser.add_argument("--skip-fstrim", action="store_true", help="Skip best-effort `sm fstrim` during Module C.")
    parser.add_argument("--skip-bg-dexopt", action="store_true", help="Skip system-wide `bg-dexopt` sweep and run only targeted `speed-profile` + fstrim.")
    parser.add_argument("--scale", type=float, default=0.5, help="Animation scale for Module D (default: 0.5).")
    parser.add_argument("--disable-blurs", action="store_true", help="Also set `disable_window_blurs=1` in Module D to reduce GPU load.")
    parser.add_argument("--host", default="adguard", help="Private DNS preset (adguard|cloudflare|quad9) or hostname.")
    parser.add_argument("--game-mode", type=int, default=2, choices=(1, 2, 3), help="Game mode (1=standard, 2=performance, 3=battery).")
    parser.add_argument("--downscale", type=float, help="Optional Game Mode resolution scale (0.3-0.9).")
    parser.add_argument("--fps", type=int, choices=(30, 45, 60, 90, 120), help="Optional FPS cap on Android 13+.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying the device.")
    parser.add_argument("--confirm", action="store_true", help="Apply without interactive prompt.")
    parser.add_argument("--skip-backup-check", action="store_true", help="Skip requiring logs/packages_backup.txt.")
    args = parser.parse_args()

    if not args.dry_run:
        ensure_dirs()
        if not args.skip_backup_check and not PACKAGES_BACKUP_PATH.exists():
            print(
                "ERROR: Pre-flight snapshot `logs/packages_backup.txt` not found. "
                "Run `python scripts/backup_packages.py` first.",
                file=sys.stderr,
            )
            return 1

    try:
        if args.module == "appops":
            if not args.packages:
                parser.error("--packages is required for `--module appops`.")
            return run_appops_module(args.packages, args.bucket, args.force_sensitive, args.serial, args.dry_run, args.confirm)
        if args.module == "freezer":
            return run_freezer_module(args.serial, args.dry_run, args.confirm)
        if args.module == "art":
            return run_art_module(args.packages, args.trim_caches, args.skip_fstrim, args.skip_bg_dexopt, args.serial, args.dry_run, args.confirm)
        if args.module == "animations":
            return run_animations_module(args.scale, args.disable_blurs, args.serial, args.dry_run, args.confirm)
        if args.module == "dns":
            return run_dns_module(args.host, args.serial, args.dry_run, args.confirm)
        if args.module == "game":
            if not args.packages:
                parser.error("--packages is required for `--module game`.")
            return run_game_module(args.packages, args.game_mode, args.downscale, args.fps, args.serial, args.dry_run, args.confirm)
    except (ValueError, AdbDeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
