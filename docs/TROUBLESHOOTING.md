# Troubleshooting & Recovery Guide

## 1. `adb devices` Shows `unauthorized`
1. Disconnect the USB cable.
2. On the phone, open **Developer options > Revoke USB debugging authorizations**.
3. Toggle **USB debugging** OFF and back ON.
4. Reconnect the cable, keep the screen unlocked, and tap **Allow** on the RSA prompt.
5. Restart the local ADB server if needed:
   ```bash
   adb kill-server && adb start-server && adb devices -l
   ```

## 2. `adb: command not found`
Install Android SDK Platform Tools and ensure the folder containing `adb` (`adb.exe` on Windows) is in your `PATH`. See [SETUP_ADB.md](./SETUP_ADB.md).

## 3. `SecurityException` When Running `settings put`, `cmd appops`, or `device_config`
- **Xiaomi / Redmi / Poco**: Enable **USB debugging (Security settings)** in Developer Options.
- **Oppo / Realme / OnePlus**: Enable **Disable permission monitoring** in Developer Options.
- **Android 14+ / Work Profiles**: Ensure you are targeting User 0 on a personal profile and not restricted by an MDM/enterprise Device Policy Controller.

## 4. `Failure [DELETE_FAILED_INTERNAL_ERROR]` During Debloat
- On ColorOS/OxygenOS/MIUI, certain vendor-protected apps cannot be uninstalled even for `--user 0`.
- Do **not** attempt forced/root removal. Leave the package installed or apply non-destructive background throttling (`python scripts/tune_performance.py --module appops --packages <pkg>`).

## 5. Accidentally Removed a Needed App (Keyboard, Gallery, Sync, etc.)
All removals in this repo use `pm uninstall -k --user 0 <pkg>`, which only hides the package for User 0 and keeps the APK on `/system`/`/product`. Restore instantly:

```bash
# Restore a single package
python scripts/restore_package.py --package <package_name>

# Restore everything recorded in logs/removed_packages.txt
python scripts/restore_package.py --all

# Or revert all recorded tweaks + packages in logs/rollback_log.json
python scripts/restore_package.py --undo-all
```
Or directly via ADB:
```bash
adb shell cmd package install-existing <package_name>
```

## 6. Device Won't Boot Properly After Removing a System Package (Bootloop / SystemUI Crash)
If USB Debugging is still reachable during boot:
1. Run `adb devices` while the phone is booting.
2. As soon as it appears as `device`, restore everything immediately:
   ```bash
   python scripts/restore_package.py --all
   adb reboot
   ```
3. If `logs/removed_packages.txt` is empty (e.g., manual commands were run), try booting into **Android Safe Mode** (hold Volume Down during boot animation) or check `logs/packages_backup.txt`.
4. If the device drops straight into OEM Recovery (`com.miui.securitycenter` or `com.xiaomi.finddevice` removed on MIUI/HyperOS) and ADB is unavailable, a factory data reset from Recovery is typically required because `/data` user-0 package state lives on the encrypted userdata partition. That is why `safety/hard_blocklist.json` and `.agents/scripts/pretool_guard.py` hard-block these packages.

## 7. Cached Apps Freezer Shows `use_freezer` Ignored
- Check `/sys/fs/cgroup/cgroup.controllers`: if `freezer` is missing, your kernel lacks cgroup v2 freezer support (common on older pre-5.4 kernels or Android 10 and earlier).
- If `freezer` is present and you ran `--module freezer --confirm`, **reboot the device**, then verify:
  ```bash
  adb shell dumpsys activity | grep -i "frozen"
  ```
  *(On Windows PowerShell: `adb shell dumpsys activity | Select-String "frozen"`)*
