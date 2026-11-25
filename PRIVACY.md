# Privacy Policy

## 100% Local Execution — Zero Telemetry

**Android AI Optimizer** runs entirely on your local machine and communicates directly with your connected Android device over local USB or local Wi-Fi ADB.

- **No Data Collection:** This project does not collect, store, or transmit your device serial numbers, installed package lists, RAM/battery dumps, or logs to any analytics service or project-operated server.
- **External Network Calls:** The only outbound request made by the scripts is `scripts/sync_uad.py` fetching the public, open-source `uad_lists.json` database from GitHub (`Universal-Debloater-Alliance/universal-android-debloater-next-generation`) into `cache/uad_lists.json`.
- **AI Provider Context:** When you run this project through Google Antigravity (or another MCP client), tool outputs you choose to inspect or share in your chat session are processed by your configured LLM provider under their respective privacy terms.
- **Git Leak Protection:** `.gitignore` is pre-configured to exclude `logs/`, `cache/`, `latest_audit.json`, `device_audit_*.json`, `packages_backup.txt`, `settings_backup.txt`, `rollback_log.json`, `removed_packages.txt`, `benchmark_before.json`, `benchmark_after.json`, and `optimization_report.md` so personal device data is never accidentally committed to GitHub.
