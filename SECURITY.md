# Security Policy

## Threat Model & Safety Architecture

Because this repository interfaces with Android devices over ADB via an AI agent (Google Antigravity / MCP), security and device integrity are enforced at the **server and hook layers**, not just in LLM prompts:

1. **Zero Raw Shell Access:** `mcp_server/server.py` exposes only 10 scoped, input-validated JSON-RPC 2.0 tools. Unrestricted `adb shell` execution is disabled by design.
2. **Strict Input Validation & Quoting:** All package names, hostnames, and arguments are validated against allowlist patterns and quoted (`shlex.quote`) before passing to `adb shell` to prevent command injection and variable expansion.
3. **Dry-Run by Default:** Every mutating MCP tool defaults to `dry_run=true` and requires explicit human confirmation (`confirm=true`, `dry_run=false`) before applying changes.
4. **Hard Blocklist Enforcement:** Critical system frameworks, launchers, IMEs, telecom services, and OEM bootloop-prone packages listed in `safety/hard_blocklist.json` are rejected at the tool layer (`mcp_server/server.py`, `scripts/debloat_packages.py`, and `.agents/scripts/pretool_guard.py`) regardless of prompt instructions.
5. **Mandatory Pre-Flight Snapshot:** Mutating tools refuse to execute unless a valid local backup snapshot (`logs/packages_backup.txt`) exists.

## Supported Versions

| Version | Supported |
| :--- | :---: |
| `0.2.x` (Latest `main`) | ✅ Yes |
| `< 0.2.0` | ❌ No |

## Reporting a Vulnerability

If you discover a command-injection vector, blocklist bypass, or unsafe ADB command in this repository:

1. **Do not open a public GitHub issue** with exploit details.
2. Use GitHub's **Private Vulnerability Reporting** feature under the **Security** tab (*Security → Advisories → Report a vulnerability*).
3. Include steps to reproduce, affected script/tool name, and Android SDK / OEM version if applicable.

We aim to acknowledge reports within 48 hours and release a patched version promptly.
