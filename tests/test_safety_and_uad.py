"""Unit and integration tests for safety blocklists, UAD-NG, AOSP tuning, rollback, hook, and MCP server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOK_SCRIPTS_DIR = REPO_ROOT / ".agents" / "scripts"
MCP_DIR = REPO_ROOT / "mcp_server"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(HOOK_SCRIPTS_DIR))
sys.path.insert(0, str(MCP_DIR))

import adb_common  # noqa: E402
import audit_device  # noqa: E402
import benchmark_device  # noqa: E402
import check_packages  # noqa: E402
import debloat_packages  # noqa: E402
import pretool_guard  # noqa: E402
import restore_package  # noqa: E402
import server as mcp_server  # noqa: E402
import sync_uad  # noqa: E402
import tune_performance  # noqa: E402


class TestConfigsAndSafety(unittest.TestCase):
    def test_repo_json_configs_are_valid(self) -> None:
        for rel in (
            ".agents/mcp_config.json",
            ".agents/mcp_config.adbmcp.example.json",
            ".agents/hooks.json",
            "safety/hard_blocklist.json",
        ):
            data = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)

        default_mcp = json.loads((REPO_ROOT / ".agents/mcp_config.json").read_text(encoding="utf-8"))
        self.assertIn("android-optimizer", default_mcp["mcpServers"])
        self.assertEqual(default_mcp["mcpServers"]["android-optimizer"]["args"], ["mcp_server/server.py"])

        example_mcp = json.loads((REPO_ROOT / ".agents/mcp_config.adbmcp.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example_mcp["mcpServers"]["adb"]["env"]["ADB_MCP_ALLOW_SHELL"], "0")

    def test_find_adb_uses_env_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_adb = Path(tmp) / ("adb.exe" if sys.platform == "win32" else "adb")
            fake_adb.write_text("", encoding="utf-8")
            with mock.patch.dict("os.environ", {"ADB_PATH": str(fake_adb)}, clear=False):
                self.assertEqual(adb_common.find_adb(), str(fake_adb))

    def test_validate_package_name(self) -> None:
        self.assertEqual(adb_common.validate_package_name("com.example.app"), "com.example.app")
        self.assertEqual(adb_common.validate_package_name("android"), "android")
        for bad in ("com.bad;rm -rf /", "com.bad && su", "", "singleword", "../etc/passwd"):
            with self.assertRaises(ValueError):
                adb_common.validate_package_name(bad)

    def test_hard_blocklist_and_sensitive_keywords(self) -> None:
        blocklist = adb_common.load_blocklist()
        for critical in (
            "com.miui.securitycenter",
            "com.xiaomi.finddevice",
            "com.android.systemui",
            "com.android.providers.contacts",
            "com.samsung.android.knox.analytics",
        ):
            blocked, reason = adb_common.is_hard_blocked(critical, blocklist)
            self.assertTrue(blocked, f"Expected {critical} to be hard-blocked")
            self.assertTrue(reason)

        blocked, _ = adb_common.is_hard_blocked("com.facebook.services", blocklist)
        self.assertFalse(blocked)

        for app in ("com.google.android.apps.nbu.paisa.user", "com.whatsapp", "com.google.android.deskclock"):
            sensitive, _ = adb_common.is_never_throttle(app, blocklist)
            self.assertTrue(sensitive, f"Expected {app} to be marked sensitive")


class TestUadNormalizationAndClassification(unittest.TestCase):
    def test_normalize_uad_dict_and_list_formats(self) -> None:
        dict_raw = {
            "com.facebook.services": {
                "list": "Misc",
                "description": "Facebook background bloatware",
                "removal": "safe",
            },
            "com.xiaomi.finddevice": {
                "list": "Oem",
                "description": "Find device daemon",
                "removal": "Unsafe",
            },
        }
        norm_dict = sync_uad.normalize_uad_database(dict_raw)
        self.assertEqual(len(norm_dict), 2)
        self.assertEqual(norm_dict["com.facebook.services"]["removal"], "Safe")

        list_raw = [
            {
                "id": "com.facebook.system",
                "list": "Misc",
                "description": "Facebook App Installer",
                "removal": "Recommended",
            }
        ]
        norm_list = sync_uad.normalize_uad_database(list_raw)
        self.assertIn("com.facebook.system", norm_list)

    def test_classify_package_prioritizes_hard_blocklist_and_surfaces_needed_by(self) -> None:
        blocklist = adb_common.load_blocklist()
        uad_db = {
            "com.miui.securitycenter": {
                "list": "Oem",
                "description": "Fake safe entry",
                "removal": "Recommended",
            },
            "com.facebook.services": {
                "list": "Misc",
                "description": "Facebook background service",
                "removal": "safe",
                "neededBy": ["com.facebook.katana"],
            },
        }
        res_blocked = check_packages.classify_package("com.miui.securitycenter", uad_db, blocklist)
        self.assertEqual(res_blocked["tier"], "Hard-Blocked")
        self.assertFalse(res_blocked["eligible"])

        res_safe = check_packages.classify_package("com.facebook.services", uad_db, blocklist)
        self.assertEqual(res_safe["tier"], "Recommended")
        self.assertTrue(res_safe["eligible"])
        self.assertIn("com.facebook.katana", res_safe["description"])


class TestDebloatAndRollback(unittest.TestCase):
    def test_debloat_blocks_unsafe_and_logs_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            backup_file = tmp_dir / "packages_backup.txt"
            backup_file.write_text("# backup\npackage:com.facebook.services\n", encoding="utf-8")
            removed_file = tmp_dir / "removed_packages.txt"
            rollback_file = tmp_dir / "rollback_log.json"
            uad_file = tmp_dir / "uad_lists.json"
            uad_file.write_text(
                json.dumps(
                    {
                        "com.facebook.services": {
                            "list": "Misc",
                            "description": "Facebook bloat",
                            "removal": "Recommended",
                        },
                        "com.oem.expertapp": {
                            "list": "Oem",
                            "description": "Expert tier feature",
                            "removal": "Expert",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(debloat_packages, "ensure_dirs"),
                mock.patch.object(debloat_packages, "PACKAGES_BACKUP_PATH", backup_file),
                mock.patch.object(adb_common, "REMOVED_PACKAGES_PATH", removed_file),
                mock.patch.object(debloat_packages, "REMOVED_PACKAGES_PATH", removed_file),
                mock.patch.object(adb_common, "ROLLBACK_LOG_PATH", rollback_file),
                mock.patch.object(check_packages, "UAD_CACHE_PATH", uad_file),
                mock.patch.object(debloat_packages, "run_adb_shell", return_value="Success\n") as adb_mock,
            ):
                rc = debloat_packages.execute_debloat(
                    ["com.miui.securitycenter", "com.oem.expertapp", "com.facebook.services"],
                    confirm=True,
                )
                self.assertEqual(rc, 0)
                adb_mock.assert_called_once_with(
                    ["pm", "uninstall", "-k", "--user", "0", "com.facebook.services"],
                    serial=None,
                    check=False,
                )

            self.assertEqual(removed_file.read_text(encoding="utf-8").strip(), "com.facebook.services")
            ledger = json.loads(rollback_file.read_text(encoding="utf-8"))
            self.assertEqual(len(ledger["actions"]), 1)
            self.assertEqual(
                ledger["actions"][0]["undo_command"],
                "adb shell cmd package install-existing com.facebook.services",
            )

            with (
                mock.patch.object(restore_package, "REMOVED_PACKAGES_PATH", removed_file),
                mock.patch.object(adb_common, "ROLLBACK_LOG_PATH", rollback_file),
                mock.patch.object(
                    restore_package,
                    "run_adb_shell",
                    return_value="Package com.facebook.services installed for user: 0\n",
                ) as restore_mock,
            ):
                rc_undo = restore_package.undo_recorded_tweaks(rollback_path=rollback_file)
                self.assertEqual(rc_undo, 0)
                restore_mock.assert_called_once_with(
                    ["cmd", "package", "install-existing", "com.facebook.services"],
                    serial=None,
                    check=False,
                )
                self.assertEqual(removed_file.read_text(encoding="utf-8").strip(), "")


class TestAuditTuneBenchmarkAndHook(unittest.TestCase):
    def test_audit_and_benchmark_parsers(self) -> None:
        mem_sample = (
            "Total PSS by process:\n"
            "  180,123K: com.android.systemui (pid 1200)\n"
            "  120,000K: com.whatsapp (pid 2200)\n"
            "Total PSS by OOM adjustment:\n"
            "Total RAM: 7,654,321K (status normal)\n"
            " Free RAM: 2,100,000K\n"
            " Used RAM: 4,200,000K\n"
        )
        mem = audit_device.parse_meminfo_summary(mem_sample)
        self.assertEqual(len(mem["top_pss_processes"]), 2)
        self.assertEqual(benchmark_device.parse_ram_kb(mem["free_ram"]), 2100000)

        df_sample = "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-5 115000000 50000000 65000000 44% /data\n"
        df_info = audit_device.parse_df_data(df_sample)
        self.assertEqual(df_info["use_percent"], "44%")
        self.assertGreater(df_info["available_gb"], 60)

        self.assertEqual(benchmark_device.parse_total_time_ms("Status: ok\nTotalTime: 418\nWaitTime: 425\n"), 418)
        self.assertEqual(benchmark_device.parse_total_time_ms("Status: ok\nWaitTime: 3178\nComplete\n"), 3178)
        with mock.patch.object(adb_common, "run_adb", return_value=mock.Mock(stdout="")) as adb_run_mock:
            adb_common.run_adb_shell(["am", "start", "-W", "com.google.android.youtube/.Shell$HomeActivity"])
            sent_args = adb_run_mock.call_args[0][0]
            self.assertIn("'com.google.android.youtube/.Shell$HomeActivity'", sent_args)
        self.assertEqual(benchmark_device.count_active_services("ServiceRecord{a}\n  ServiceRecord{b}\n"), 2)
        self.assertEqual(benchmark_device.count_frozen_processes("frozen=true\nApps frozen:\n"), 2)

        report = benchmark_device.render_comparison_report(
            {
                "captured_at": "2026-01-01T00:00:00+00:00",
                "free_ram_kb": 1024000,
                "used_ram_kb": 4096000,
                "active_service_records": 40,
                "cold_starts": [{"package": "com.example.app", "total_time_ms": 600}],
            },
            {
                "captured_at": "2026-01-01T00:10:00+00:00",
                "free_ram_kb": 1536000,
                "used_ram_kb": 3584000,
                "active_service_records": 28,
                "cold_starts": [{"package": "com.example.app", "total_time_ms": 420}],
            },
        )
        self.assertIn("-180 ms", report)
        self.assertIn("+512000 KB", report)

    def test_tune_aosp_version_awareness_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rollback_file = Path(tmp) / "rollback_log.json"

            # 1. AppOps skips sensitive whatsapp and records exact prior 'default' mode on SDK 33
            def fake_shell_appops(args, serial=None, check=True, timeout=60):
                if args[:2] == ["getprop", "ro.build.version.sdk"]:
                    return "33\n"
                if args[:3] == ["cmd", "appops", "get"]:
                    return "No operations.\n"
                if args[:2] == ["am", "get-standby-bucket"]:
                    return "working_set\n"
                return ""

            with (
                mock.patch.object(adb_common, "ROLLBACK_LOG_PATH", rollback_file),
                mock.patch.object(tune_performance, "run_adb_shell", side_effect=fake_shell_appops) as adb_mock,
            ):
                self.assertEqual(
                    tune_performance.run_appops_module(["com.whatsapp"], "rare", False, None, False, True),
                    1,
                )
                self.assertEqual(
                    tune_performance.run_appops_module(["com.shop.app"], "restricted", False, None, False, True),
                    0,
                )
                self.assertTrue(adb_mock.called)

            ledger = json.loads(rollback_file.read_text(encoding="utf-8"))
            self.assertEqual(ledger["actions"][0]["undo_args"], ["cmd", "appops", "set", "com.shop.app", "RUN_ANY_IN_BACKGROUND", "default"])
            self.assertEqual(ledger["actions"][2]["undo_args"], ["am", "set-standby-bucket", "com.shop.app", "working_set"])

            # 2. Freezer sets both cached_apps_freezer and use_freezer
            calls: list[list[str]] = []

            def fake_shell_freezer(args, serial=None, check=True, timeout=60):
                calls.append(args)
                if args[:2] == ["getprop", "ro.build.version.sdk"]:
                    return "34\n"
                if args[:2] == ["cat", "/sys/fs/cgroup/cgroup.controllers"]:
                    return "cpu io memory freezer\n"
                if args[:2] == ["device_config", "get"]:
                    return "null\n"
                if args[:2] == ["settings", "get"]:
                    return "device_default\n"
                return ""

            with (
                mock.patch.object(adb_common, "ROLLBACK_LOG_PATH", rollback_file),
                mock.patch.object(tune_performance, "run_adb_shell", side_effect=fake_shell_freezer),
            ):
                self.assertEqual(tune_performance.run_freezer_module(None, False, True), 0)
            self.assertIn(["settings", "put", "global", "cached_apps_freezer", "enabled"], calls)
            self.assertIn(["device_config", "put", "activity_manager_native_boot", "use_freezer", "true"], calls)

            # 3. ART uses pm art on SDK 34, skips trim-caches unless opted in, handles sm fstrim SecurityException
            art_calls: list[list[str]] = []

            def fake_shell_art(args, serial=None, check=True, timeout=60):
                art_calls.append(args)
                if args[:2] == ["getprop", "ro.build.version.sdk"]:
                    return "34\n"
                if args == ["sm", "fstrim"]:
                    return "SecurityException: Permission denial"
                return "Success\n"

            with mock.patch.object(tune_performance, "run_adb_shell", side_effect=fake_shell_art):
                self.assertEqual(tune_performance.run_art_module([], False, False, False, None, False, True), 0)
            self.assertIn(["pm", "art", "dexopt-packages", "-r", "bg-dexopt"], art_calls)
            self.assertNotIn(["pm", "trim-caches", "100G"], art_calls)

            # Verify TimeoutExpired on bg-dexopt continues gracefully to targeted speed-profile
            timeout_calls: list[list[str]] = []

            def fake_shell_art_timeout(args, serial=None, check=True, timeout=60):
                timeout_calls.append(args)
                if args[:2] == ["getprop", "ro.build.version.sdk"]:
                    return "34\n"
                if args[:3] == ["pm", "art", "dexopt-packages"]:
                    raise subprocess.TimeoutExpired(cmd="adb", timeout=600)
                return "Success\n"

            with mock.patch.object(tune_performance, "run_adb_shell", side_effect=fake_shell_art_timeout):
                self.assertEqual(
                    tune_performance.run_art_module(["com.whatsapp"], False, True, False, None, False, True),
                    0,
                )
            self.assertIn(["cmd", "package", "compile", "-m", "speed-profile", "-f", "com.whatsapp"], timeout_calls)

            # 4. Game Mode uses cmd game set on SDK 34 vs cmd game downscale on SDK 31
            game34_calls: list[list[str]] = []

            def fake_shell_game34(args, serial=None, check=True, timeout=60):
                game34_calls.append(args)
                if args[:2] == ["getprop", "ro.build.version.sdk"]:
                    return "34\n"
                return ""

            with (
                mock.patch.object(adb_common, "ROLLBACK_LOG_PATH", rollback_file),
                mock.patch.object(tune_performance, "run_adb_shell", side_effect=fake_shell_game34),
            ):
                self.assertEqual(tune_performance.run_game_module(["com.game.id"], 2, 0.8, 60, None, False, True), 0)
            self.assertIn(["cmd", "game", "set", "--downscale", "0.8", "--fps", "60", "com.game.id"], game34_calls)

    def test_pretool_guard_hook_decisions(self) -> None:
        self.assertEqual(pretool_guard.evaluate_command("git status")["decision"], "allow")
        self.assertEqual(pretool_guard.evaluate_command("adb devices -l")["decision"], "allow")
        self.assertEqual(
            pretool_guard.evaluate_command("python scripts/debloat_packages.py --dry-run com.foo.bar")["decision"],
            "allow",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("adb shell cmd package compile -m everything -a")["decision"],
            "deny",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("adb shell pm uninstall -k --user 0 com.miui.securitycenter")["decision"],
            "deny",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("adb shell pm uninstall com.facebook.services")["decision"],
            "deny",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("adb shell pm uninstall -k --user 0 com.facebook.services")["decision"],
            "force_ask",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("adb shell pm art dexopt-packages -r bg-dexopt")["decision"],
            "force_ask",
        )
        self.assertEqual(
            pretool_guard.evaluate_command("python scripts/tune_performance.py --module animations --confirm")["decision"],
            "force_ask",
        )

    def test_pretool_guard_cli_stdin_stdout(self) -> None:
        guard_script = REPO_ROOT / ".agents" / "scripts" / "pretool_guard.py"
        cases = [
            ("adb shell pm uninstall -k --user 0 com.miui.securitycenter", "deny"),
            ("adb shell pm uninstall -k --user 0 com.facebook.services", "force_ask"),
            ("adb devices -l", "allow"),
        ]
        for cmd, expected in cases:
            payload = json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": cmd}}})
            proc = subprocess.run(
                [sys.executable, str(guard_script)],
                input=payload,
                capture_output=True,
                text=True,
                check=True,
            )
            out = json.loads(proc.stdout)
            self.assertEqual(out["decision"], expected)


class TestMcpServerStdio(unittest.TestCase):
    def test_mcp_stdio_handshake_tools_list_and_safety_gates(self) -> None:
        server_path = REPO_ROOT / "mcp_server" / "server.py"
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "android_debloat_packages",
                    "arguments": {"packages": ["com.miui.securitycenter"], "dry_run": False, "confirm": False},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "android_debloat_packages",
                    "arguments": {"packages": ["com.miui.securitycenter"], "dry_run": True},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "android_debloat_packages",
                    "arguments": {"packages": ["com.facebook.services"], "dry_run": False, "confirm": True},
                },
            },
        ]
        stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        with tempfile.TemporaryDirectory() as isolated_logs:
            env = {
                **os.environ,
                "ANDROID_OPTIMIZER_LOGS_DIR": isolated_logs,
                "ADB_SERIAL": "TEST-NO-DEVICE",
            }
            proc = subprocess.run(
                [sys.executable, str(server_path)],
                input=stdin_payload,
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
        lines = [json.loads(line) for line in proc.stdout.strip().splitlines()]
        self.assertEqual(len(lines), 5)  # notification yields no response
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "android-ai-optimizer")
        tool_names = [t["name"] for t in lines[1]["result"]["tools"]]
        self.assertEqual(len(tool_names), 10)
        self.assertNotIn("run_shell", tool_names)

        # Call 3: confirm=false with dry_run=false is rejected
        self.assertTrue(lines[2]["result"]["isError"])
        # Call 4: dry_run on hard-blocked package reports HARD-BLOCKED and non-zero exit_code
        payload4 = json.loads(lines[3]["result"]["content"][0]["text"])
        self.assertEqual(payload4["exit_code"], 1)
        self.assertIn("HARD-BLOCKED", payload4["output"])
        # Call 5: mutating call without backup snapshot is rejected cleanly
        payload5 = json.loads(lines[4]["result"]["content"][0]["text"])
        self.assertEqual(payload5["exit_code"], 1)
        self.assertIn("packages_backup.txt", payload5["output"])

        # Sanity check direct handle_request unknown tool
        unknown = mcp_server.handle_request({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "bogus"}})
        self.assertIsNotNone(unknown)
        self.assertIn("error", unknown)


if __name__ == "__main__":
    unittest.main()
