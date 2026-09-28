#  Karis-NAS 1.0

A modern, Apple-inspired personal cloud storage dashboard, media streaming portal, and private communications hub. Designed with authentic macOS Sonoma aesthetics, liquid glassmorphism, client-side end-to-end encrypted messaging, and native file management.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-success.svg)
![Python](https://img.shields.io/badge/python-3.8+-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)
![Design](https://img.shields.io/badge/style-Apple%20Sonoma%20%2F%20iOS%20HIG-black.svg)

---

## ✨ Overview

**Karis-NAS** turns any PC, mini server, home lab box, or spare laptop into a personal cloud and NAS server. Everything is self-hosted on your own local network, giving you full ownership and control over your files, media, and private chats with zero subscription fees, zero cloud telemetry, and zero tracking.

---

## 🚀 Key Features

###  Apple Design System
* **Authentic Sonoma & iOS Aesthetics**: Liquid glassmorphism (`backdrop-filter: blur(20px)`), 24px squircle border radiuses, and SF Pro typography.
* **17 Calibrated Themes**: Light, Dark, OLED Pure Black, Midnight Navy, Space Gray, Cupertino Blue, Forest Pine, Cyber Violet, Sunset Rose, and more.
* **Dynamic Island & Desktop Nav**: Floating capsule status pill displaying live clock, weather, active user avatar, and unread badges.
* **Native iOS Mobile Dock**: Floating bottom tab bar dock (`max-width: 440px`) with full iPhone/iPad safe-area inset support.

### 📁 macOS Finder File Management
* **Segmented Breadcrumbs**: Navigate deep folder hierarchies with intuitive clickable path segments.
* **Real-Time Client-Side Search**: Instant search filtering across files and folders without server roundtrips.
* **Multi-File Drag-and-Drop**: Upload single files or bulk batches directly into any active folder.
* **Inline Code & Text Editor**: Edit `.txt`, `.md`, `.json`, `.py`, `.js`, `.html`, `.css`, and config files directly in the browser.
* **Custom Storage Root Mapping**: Configure your storage root to any local or external hard drive (e.g. `D:\NAS_Storage` or `C:\Users\<Name>\Documents`).

### 👁 Apple QuickLook Media Previews
* **Audio Player**: Interactive playback with an animated rotating vinyl disc and time scrubber.
* **Video Streaming**: HTTP 206 Partial Content range requests for instant seeking and smooth playback.
* **Photo Viewer**: High-resolution image inspection with zoom and rotation controls.
* **Document & Code Inspection**: Syntax-highlighted text preview with line numbers and a 1-click clipboard copy button.

### 🔒 Client-Side End-to-End Encrypted (E2EE) Messaging
* **Zero-Knowledge Security**: Messages are encrypted directly in the client browser using the WebCrypto API (AES-GCM 256-bit) before transmission.
* **No Plaintext on Disk**: The server only stores encrypted ciphertext and initialization vectors (IVs). Server administrators cannot read private messages.
* **Interactive Tapbacks**: Express reactions (❤️, 👍, 👎, 😂, ‼️, ❓) attached to any message.
* **Web Audio Synthetic Chime**: High-fidelity sound effects on sent and received messages using the browser's native Web Audio API (no external MP3 assets required).
* **Delivery Indicators**: Real-time read receipts (`✓ Sent`, `✓✓ Read`) and unread notification badges.

### 📊 Live Activity Monitor & Telemetry
* **Hardware Gauges**: Real-time CPU usage, RAM utilization, and disk storage capacity.
* **Animated Sonar Pulse**: Visual status beacon showing live server health and process heartbeat.
* **Multi-IP Network Detection**: Shows active LAN and Wi-Fi IP addresses for easy device connection.

### 🔄 1-Click GitHub Auto-Updater
* **SemVer 2.0 Version Comparator**: Checks releases against GitHub without false alerts.
* **60-Second Countdown Warning**: Circular countdown modal warning active users before a reboot.
* **Detached Background Restart**: Updates and restarts the server cleanly without orphaned processes.

### 👥 User Administration & Storage Quotas
* **Role-Based Access Control**: Differentiate between Administrators and standard Users.
* **Granular Quota Limits**: Set individual storage quotas (e.g., 25 GB, 50 GB, or Unlimited).
* **Secure Authentication**: Passwords hashed using industry-standard Werkzeug scrypt/PBKDF2.

### 🧙‍♂️ First-Run Setup Wizard (`/setup`)
* 4-step onboarding flow guiding you through administrator account creation, storage limits, and weather configuration by US ZIP code.

---

## 📦 Quick Start & Installation

### Option 1: 1-Click Windows Setup (Recommended)

1. Download or extract **`KarisNAS1.0.zip`** to a temporary folder.
2. Double-click **`install.bat`** (or open Command Prompt and run `python installer.py`).
3. The setup assistant will:
   * Install required dependencies (`Flask`, `psutil`, `werkzeug`).
   * Deploy the server to **`C:\KarisNAS1.0`** (or your custom directory).
   * Optionally configure silent Windows boot autostart via `KarisNAS.vbs`.
   * Automatically launch the server in the background.
4. Open your browser:
   * Local: **`http://localhost:3251`**
   * Network: **`http://<your-server-ip>:3251`**

### Option 2: Linux / macOS Installation

```bash
# 1. Clone repository
git clone https://github.com/fanumtalkstech/Karis-NAS.git
cd Karis-NAS

# 2. Run the deployment installer
python3 installer.py

# Or start directly
pip install -r requirements.txt
python3 app.py
```

---

## ⚙️ Configuration

Karis-NAS stores settings in `config.json` inside your installation folder (`C:\KarisNAS1.0`):

```json
{
  "current_version": "1.0",
  "port": 3251,
  "github_repo": "fanumtalkstech/Karis-NAS",
  "check_github_updates_hourly": true,
  "beta_mode": false,
  "weather_zip": "45631",
  "weather_lat": 38.8098,
  "weather_lon": -82.2104,
  "features": {
    "messaging": true,
    "system_monitor": true,
    "weather": true,
    "notes": true
  }
}
```

### Storage Directory Mapping
By default, files are stored in `C:\KarisNAS1.0\storage`. Administrators can update this to any internal or external drive at any time in **Settings → Storage Folder**, or by setting the `KARIS_BASE_DIR` environment variable.

---

## 📱 Mobile & PWA Access

Karis-NAS is built as a Progressive Web App (PWA):
1. Open `http://<your-server-ip>:3251` on your iPhone (Safari) or Android (Chrome).
2. Tap the **Share** button on iOS (or menu on Android) and choose **"Add to Home Screen"**.
3. Launch Karis-NAS directly from your home screen for a full-screen, standalone native app experience.

---

## 🔒 Security Architecture

* **Local-First Architecture**: Your files and data remain exclusively on your local storage.
* **Encrypted Messaging**: Private chats utilize client-side WebCrypto AES-GCM 256-bit encryption. The server stores only encrypted payloads.
* **Atomic File Writes**: Windows-safe atomic JSON file persistence prevents data corruption during unexpected shutdowns or restarts.
* **Path Traversal Protection**: All file operations validate canonical paths against user root folders to prevent directory traversal attacks.

For more details, see our [SECURITY.md](SECURITY.md) and [PRIVACY_POLICY.md](PRIVACY_POLICY.md).

---

## 📂 Project Structure

```text
KarisNAS1.0/
├── app.py                 # Core Flask backend server and API routes
├── installer.py           # Automated deployment and update assistant
├── install.bat            # 1-click Windows installer launcher
├── run.bat                # Direct server start script
├── requirements.txt       # Python dependencies (Flask, psutil)
├── README.md              # Documentation and setup guide
├── PRIVACY_POLICY.md      # Self-hosted privacy policy
├── SECURITY.md            # Security disclosures and architecture
├── CONTRIBUTING.md        # Contribution guidelines
├── CHANGELOG.md           # Version release history
├── LICENSE                # MIT License
└── templates/
    ├── dashboard.html     # Main Apple Sonoma desktop & mobile UI
    ├── settings.html      # System preferences and admin portal
    ├── setup.html         # First-run onboarding wizard
    ├── login.html         # Glassmorphic authentication portal
    └── error.html         # Custom status and diagnostic page
```

---

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
