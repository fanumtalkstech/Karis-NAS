# Privacy Policy for Karis-NAS

**Effective Date:** September 28, 2026  
**Application Version:** 1.0.0

Karis-NAS is an open-source, self-hosted personal cloud storage and media server designed from the ground up with a **local-first, privacy-by-design** philosophy. We believe your files, conversations, and personal data belong exclusively to you.

---

## 1. Core Principles

1. **100% Self-Hosted**: Karis-NAS runs on your own hardware (PC, home lab, server, or mini PC). All files, user profiles, credentials, and settings remain on your local storage drive (`C:\KarisNAS1.0` or your custom designated folder).
2. **Zero Telemetry & Zero Analytics**: Karis-NAS contains **no** telemetry, **no** tracking cookies, **no** usage analytics, **no** advertising SDKs, and **no** third-party tracking scripts.
3. **No Centralized Servers**: There are no central servers collecting logs, IP addresses, or metadata about your installation. The developers of Karis-NAS have no access to your installation, files, or user accounts.

---

## 2. Information Handled by Your Local Server

Because Karis-NAS runs on your own equipment, any information stored is kept under your direct physical and administrative control:

### A. User Accounts & Authentication
* **Account Credentials**: Usernames, roles (Admin/User), and profile settings are stored locally in `users.json`.
* **Password Protection**: Passwords are never stored in plaintext. They are hashed using cryptographic salt algorithms (scrypt/PBKDF2) provided by Python's `werkzeug.security` library.
* **Session Security**: Session tokens are cryptographically generated and stored with `SameSite=Lax` and `HttpOnly` attributes to mitigate cross-site scripting (XSS) risks.

### B. Uploaded Files and Media
* Files uploaded to Karis-NAS are written directly to your local file system under the designated storage root directory.
* Files are never indexed, duplicated, scanned, or transferred to any external cloud provider.

### C. End-to-End Encrypted (E2EE) Messaging
* **Client-Side Encryption**: Messages sent through the integrated messaging system are encrypted directly within your web browser using the browser's native **WebCrypto API** (AES-GCM with 256-bit symmetric keys) prior to transmission over your local network.
* **Zero Plaintext Storage**: The backend server (`app.py`) only receives and stores the initialization vector (IV) and the encrypted ciphertext in `messages.json`. The host server operator cannot read the contents of private messages without the decryption passphrase.
* **Ephemeral Message Deletion**: When a user deletes a message, its ciphertext is permanently overwritten and purged from `messages.json`.

---

## 3. External Network Connections

Karis-NAS is engineered to operate in air-gapped or offline local network environments. By default, the application initiates external outbound HTTP connections only for two optional features:

### A. Local Weather Forecasts (Open-Meteo)
* If the weather widget is enabled, the server queries the public Open-Meteo API (`https://api.open-meteo.com`) to retrieve current temperature and weather conditions based on your configured US ZIP code or latitude/longitude coordinates.
* **Privacy Impact**: No personal identifiers, IP addresses of client devices, or user account information are transmitted.
* **Control**: You can disable the weather widget at any time in **Settings → Optional Features**, preventing any weather-related outbound network requests.

### B. GitHub Release Updates
* If automatic update checks are enabled, the server periodically queries the public GitHub REST API (`https://api.github.com/repos/fanumtalkstech/Karis-NAS/releases/latest`) to check if a newer version of Karis-NAS has been published.
* **Privacy Impact**: This query only retrieves public release metadata (tag names and changelogs). No user data or system telemetry is sent.
* **Control**: You can disable hourly GitHub update checks in **Settings → Software Update**, fully suppressing update requests.

---

## 4. Local Network & Mobile Device Access

* When accessing Karis-NAS from other devices on your local Wi-Fi network (such as an iPhone, iPad, laptop, or Android device), traffic travels directly between your client device and your host machine over your local area network (LAN).
* For enhanced security across Wi-Fi networks, administrators may supply custom SSL/TLS certificates (`cert.pem` and `key.pem`) to enable HTTPS encryption for all local traffic.

---

## 5. Data Retention & User Control

As the owner of your Karis-NAS instance, you have full ownership and total control over your data:
* **Data Portability & Backup**: All server data lives in plain JSON files and standard directories (`storage/`, `users.json`, `config.json`, `shares.json`, `messages.json`). You can copy, back up, or migrate your entire installation by copying the `C:\KarisNAS1.0` folder.
* **Complete Erasure**: Deleting the `C:\KarisNAS1.0` directory permanently and irreversibly erases all accounts, messages, configurations, and files from your system.

---

## 6. Children's Privacy

Karis-NAS does not collect personal information from any user, including children under the age of 13. Household and educational network administrators maintain sole discretion over who is granted user accounts on their local instance.

---

## 7. Open Source Verification

Because Karis-NAS is 100% open source, you and the security community are encouraged to inspect and audit the complete source code (`app.py`, `installer.py`, and HTML templates) to independently verify all claims made in this Privacy Policy.

---

## 8. Changes to This Policy

Any revisions or updates to this Privacy Policy will be documented directly in this repository and accompanied by an update in the project's [CHANGELOG.md](CHANGELOG.md).

---

## 9. Contact & Inquiries

For questions, security disclosures, or concerns regarding Karis-NAS, please open an issue on the official GitHub repository:
* **Repository**: [https://github.com/fanumtalkstech/Karis-NAS](https://github.com/fanumtalkstech/Karis-NAS)
