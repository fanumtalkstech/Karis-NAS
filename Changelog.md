# Changelog

All notable changes to **Karis-NAS** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-28

### 🎉 Initial Official Stable Release

####  Apple Design System & User Interface
* **macOS Sonoma Aesthetic**: Liquid glassmorphism with high-saturation backdrops (`backdrop-filter: blur(20px)`), 24px squircles, and SF Pro typography.
* **17 Calibrated Color Themes**: Light, Dark, OLED Pure Black, Midnight Navy, Space Gray, Cupertino Blue, Forest Pine, Cyber Violet, Sunset Rose, and more.
* **Desktop Dynamic Island**: Floating capsule status pill displaying live system clock, weather status, user profile avatar, and unread message indicators.
* **Native iOS Mobile Dock**: Floating bottom tab bar dock (`max-width: 440px`) optimized for iPhone and Android devices with safe-area inset support.

#### 📁 macOS Finder File Explorer
* **Breadcrumb Navigation**: Segmented capsule path bar for navigating nested directories.
* **Client-Side Search**: Instant search filtering across files and folders without server roundtrips.
* **Drag-and-Drop Uploads**: Support for single and multi-file drag-and-drop batch uploads.
* **Inline File Editor**: Real-time browser-based text/code editor for `.txt`, `.md`, `.json`, `.py`, `.js`, `.html`, `.css`, and configuration files.
* **Storage Root Customization**: Support for remapping the storage directory to any internal or external drive (`C:\KarisNAS1.0\storage` or custom drives).

#### 👁 Apple QuickLook Media Player
* **Vinyl Audio Player**: Interactive music player featuring an animated rotating vinyl disc, track progress scrubber, and playback controls.
* **HTTP 206 Partial Content Video Streaming**: Native range-request video streaming enabling instant seeking and low-latency playback.
* **High-Res Photo Viewer**: Image viewer with zoom, rotation, and full-screen preview.
* **Syntax Text Inspection**: Code and document viewer with line numbers and 1-click clipboard copy.

#### 🔒 Client-Side End-to-End Encrypted (E2EE) Messaging
* **Zero-Knowledge Architecture**: In-browser client-side encryption powered by the WebCrypto API (AES-GCM 256-bit). Server stores zero plaintext.
* **Interactive Tapbacks**: Quick emoji reaction pills (❤️, 👍, 👎, 😂, ‼️, ❓) attached to chat bubbles.
* **Web Audio Synthetic Chime**: High-fidelity sound effects generated dynamically via Web Audio API without external audio assets.
* **Read Receipts & Badges**: Delivery indicators (`✓ Sent`, `✓✓ Read`) with unread count badges in the navigation bar.

#### 📊 Live Activity Monitor & Telemetry
* **Hardware Gauges**: Real-time visual meters tracking host CPU utilization, RAM usage, and storage capacity.
* **Animated Sonar Pulse**: Visual status beacon indicating server health and process heartbeat.
* **Network IP Detection**: Automatic detection and display of local network and Wi-Fi IP addresses for seamless client connections.

#### 🔄 1-Click GitHub Auto-Updater
* **SemVer 2.0 Comparator**: Accurate release tag checking avoiding false update notices.
* **60-Second Countdown Modal**: Visual countdown ring warning connected users prior to a server update.
* **Detached Background Restart**: Safe server restart mechanism ensuring smooth handover without orphaned processes.

#### 🛠 Deployment & Administration
* **1-Click Setup**: Automated `install.bat` and `installer.py` deployment wizard targeting `C:\KarisNAS1.0`.
* **Silent Windows Autostart**: Optional creation of `KarisNAS.vbs` in the Windows Startup folder for invisible background server execution on boot.
* **Role-Based User Management**: User account administration with granular storage quotas and secure scrypt/PBKDF2 password hashing.
* **First-Run Setup Wizard (`/setup`)**: 4-step onboarding flow for configuring administrator credentials, storage limits, and weather preferences.
* **Windows-Safe Concurrency**: Atomic file operations with thread locks and unique temporary file replacement, mitigating `[WinError 32]` collisions.
