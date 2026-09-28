#!/usr/bin/env python3
import os
import sys
import shutil
import json
import subprocess
import socket
import datetime

PORT = 3251

def get_all_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    try:
        host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        for ip in host_ips:
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    try:
        import psutil
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ips.add(addr.address)
    except Exception:
        pass

    return sorted(list(ips))

def check_python():
    if sys.version_info < (3, 8):
        print(f"[ERROR] Python 3.8 or higher is required. You are running Python {sys.version.split()[0]}.")
        sys.exit(1)

def configure_autostart_at_boot(target_dir):
    print("\n[?] Boot Autostart:")
    try:
        ans = input("    Start Karis-NAS automatically when your computer boots? [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return

    if ans in ('', 'y', 'yes'):
        if os.name == 'nt':
            try:
                startup_folder = os.path.join(
                    os.environ.get('APPDATA', ''),
                    r'Microsoft\Windows\Start Menu\Programs\Startup'
                )
                if os.path.exists(startup_folder):
                    vbs_path = os.path.join(startup_folder, "KarisNAS.vbs")
                    bat_path = os.path.join(target_dir, "start.bat")
                    with open(vbs_path, "w") as f:
                        f.write('Set WshShell = CreateObject("WScript.Shell")\n')
                        f.write(f'WshShell.Run chr(34) & "{bat_path}" & chr(34), 0\n')
                        f.write('Set WshShell = Nothing\n')
                    print("    ✓ Windows Startup configured (runs silently in background at boot).")
            except Exception as e:
                print(f"    [!] Could not configure startup shortcut: {e}")
        else:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            try:
                os.makedirs(autostart_dir, exist_ok=True)
                desktop_file = os.path.join(autostart_dir, "karis-nas.desktop")
                with open(desktop_file, "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=Karis-NAS\n")
                    f.write(f'Exec="{sys.executable}" "{os.path.join(target_dir, "app.py")}"\n')
                    f.write("Hidden=false\nX-GNOME-Autostart-enabled=true\n")
                print("    ✓ Desktop autostart configured.")
            except Exception:
                pass
    else:
        print("    Autostart skipped.")

def start_server_process(target_dir):
    print("\n[*] Starting Karis-NAS 1.0 server...")
    app_script = os.path.join(target_dir, "app.py")
    try:
        if os.name == 'nt':
            subprocess.Popen([sys.executable, app_script], cwd=target_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([sys.executable, app_script], cwd=target_dir, start_new_session=True)
        print("    ✓ Server process started.")
    except Exception as e:
        print(f"    [!] Could not start process automatically: {e}")

def main():
    print("===============================================================================")
    print("  Karis-NAS 1.0 - Installer & Updater")
    print("===============================================================================\n")

    check_python()

    source_dir = os.path.dirname(os.path.abspath(__file__))
    default_dest = r"C:\KarisNAS1.0" if os.name == 'nt' else os.path.expanduser("~/KarisNAS1.0")

    while True:
        try:
            user_input = input(f"Install location [Default: {default_dest}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            sys.exit(1)

        target_dir = os.path.abspath(user_input) if user_input else default_dest

        existing_app = os.path.join(target_dir, "app.py")
        existing_cfg = os.path.join(target_dir, "config.json")
        is_existing = os.path.exists(existing_app) or os.path.exists(existing_cfg)

        if is_existing:
            print(f"\n[!] Existing installation found at: {target_dir}")
            try:
                choice = input("    Update to Karis-NAS 1.0? [Y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                sys.exit(1)

            if choice in ('', 'y', 'yes'):
                is_update_mode = True
                break
            else:
                print("\nPlease choose a different directory for a fresh install.\n")
                continue
        else:
            is_update_mode = False
            break

    os.makedirs(target_dir, exist_ok=True)
    target_templates = os.path.join(target_dir, "templates")
    os.makedirs(target_templates, exist_ok=True)

    source_templates = os.path.join(source_dir, "templates")

    # Files to install/update
    core_files = ["app.py", "requirements.txt", "install.bat", "run.bat", "installer.py", "README.md"]

    if is_update_mode:
        print(f"\n[1/3] Creating safety backup of existing code...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(target_dir, "backups", f"backup_{timestamp}")
        try:
            os.makedirs(backup_dir, exist_ok=True)
            if os.path.exists(existing_app):
                shutil.copy2(existing_app, os.path.join(backup_dir, "app.py"))
            if os.path.exists(target_templates):
                shutil.copytree(target_templates, os.path.join(backup_dir, "templates"), dirs_exist_ok=True)
            print(f"      ✓ Backup saved to: backups/backup_{timestamp}")
        except Exception as e:
            print(f"      [!] Backup notice: {e}")

        print("\n[2/3] Updating system files...")
        for fname in core_files:
            src = os.path.join(source_dir, fname)
            dst = os.path.join(target_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"      ✓ Updated {fname}")

        if os.path.exists(source_templates):
            for tname in os.listdir(source_templates):
                tsrc = os.path.join(source_templates, tname)
                tdst = os.path.join(target_templates, tname)
                if os.path.isfile(tsrc):
                    shutil.copy2(tsrc, tdst)
                    print(f"      ✓ Updated templates/{tname}")

        print("      ✓ User data preserved (users.json, config.json, storage, messages untouched).")
    else:
        print(f"\n[1/3] Setting up directories at: {target_dir}")
        os.makedirs(os.path.join(target_dir, "storage"), exist_ok=True)
        os.makedirs(os.path.join(target_dir, "avatars"), exist_ok=True)
        os.makedirs(os.path.join(target_dir, "chat_attachments"), exist_ok=True)

        print("\n[2/3] Copying files...")
        for fname in core_files:
            src = os.path.join(source_dir, fname)
            dst = os.path.join(target_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"      ✓ Copied {fname}")

        if os.path.exists(source_templates):
            for tname in os.listdir(source_templates):
                tsrc = os.path.join(source_templates, tname)
                tdst = os.path.join(target_templates, tname)
                if os.path.isfile(tsrc):
                    shutil.copy2(tsrc, tdst)
                    print(f"      ✓ Copied templates/{tname}")

        # Initial clean config
        cfg_file = os.path.join(target_dir, "config.json")
        default_docs = os.path.join(os.path.expanduser("~"), "Documents")
        initial_config = {
            "demo_mode": False,
            "setup_completed": False,
            "beta_mode": False,
            "storage_folder": default_docs,
            "weather_location": "Gallipolis, OH",
            "weather_zip": "45631",
            "weather_lat": 38.8098,
            "weather_lon": -82.2104,
            "github_repo": "fanumtalkstech/Karis-NAS",
            "check_github_updates_hourly": True,
            "current_version": "1.0",
            "features": {
                "messaging": True,
                "system_monitor": True,
                "weather": True,
                "notes": True
            }
        }
        with open(cfg_file, "w") as f:
            json.dump(initial_config, f, indent=4)

        users_file = os.path.join(target_dir, "users.json")
        with open(users_file, "w") as f:
            json.dump({}, f, indent=4)

    # Launcher batch script for Windows
    if os.name == 'nt':
        start_bat = os.path.join(target_dir, "start.bat")
        with open(start_bat, "w") as f:
            f.write('@echo off\n')
            f.write('title Karis-NAS 1.0 Server\n')
            f.write('cd /d "%~dp0"\n')
            f.write('echo Starting Karis-NAS 1.0...\n')
            f.write(f'"{sys.executable}" app.py\n')
            f.write('pause\n')

    # Install pip dependencies
    print("\n[3/3] Checking dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "psutil"], stdout=subprocess.DEVNULL)
        print("      ✓ Dependencies installed (flask, psutil).")
    except Exception:
        pass

    configure_autostart_at_boot(target_dir)
    start_server_process(target_dir)

    lan_ips = get_all_ips()
    action_label = "UPDATED" if is_update_mode else "INSTALLED"

    print("\n" + "=" * 76)
    print(f"  ✓ KARIS-NAS 1.0 {action_label} SUCCESSFULLY!")
    print("=" * 76)
    print(f"  Location: {target_dir}")
    print("\n  ACCESS URLS:")
    print(f"    🖥️  This Computer:     http://localhost:{PORT}")
    for ip in lan_ips:
        print(f"    📱  Phone / iPad / LAN: http://{ip}:{PORT}")
    if not lan_ips:
        print(f"    📱  Phone / iPad / LAN: http://<your-local-ip>:{PORT}")

    if not is_update_mode:
        print("\n  👉 Open any link above in your browser to complete initial setup!")
    else:
        print("\n  👉 Open any link above to access your dashboard!")
    print("=" * 76 + "\n")

if __name__ == "__main__":
    main()
