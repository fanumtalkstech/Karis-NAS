# Security Policy for Karis-NAS

Karis-NAS takes the security and integrity of your self-hosted data seriously. This document outlines our security architecture, supported versions, and how to report vulnerabilities.

---

## Supported Versions

Only the latest release of Karis-NAS receives security updates and bug fixes:

| Version | Supported          | Status             |
| ------- | ------------------ | ------------------ |
| 1.0.x   | :white_check_mark: | Active / Current   |
| < 1.0   | :x:                | Deprecated / EOL   |

---

## Security Architecture & Defenses

### 1. Password Storage & Authentication
* Passwords are never stored in plaintext. They are salted and hashed using `werkzeug.security.generate_password_hash` with scrypt/PBKDF2.
* Session cookies utilize `HttpOnly` and `SameSite=Lax` flags to prevent client-side script interception.

### 2. Client-Side End-to-End Encryption (E2EE)
* Messaging uses the W3C **WebCrypto API** directly in the user's web browser.
* Encryption is performed via **AES-GCM (256-bit key)** with a cryptographically secure 12-byte initialization vector (IV) generated per message using `crypto.getRandomValues()`.
* The server acts strictly as an encrypted message relay and persistence vault; it never has access to the cryptographic keys required to decipher user messages.

### 3. Path Traversal & File Access Controls
* All file access operations (`read`, `write`, `delete`, `share`, `download`) resolve the canonical absolute path using `os.path.abspath()` and verify that the target directory strictly begins with the authorized user root or shared directory:
  ```python
  if not abs_path.startswith(user_root):
      abort(403)
  ```
* Prohibits path manipulation attacks (`../`, symlink jumping, or hidden system folder access).

### 4. Windows-Safe Atomic File Locking
* To prevent JSON corruption or file-sharing lock violations (`[WinError 32]` on Windows), file updates write to a unique temporary file (`*.tmp_<token>_<thread>_<timestamp>`) and perform atomic replacement (`os.replace`) backed by thread locks and exponential retry fallbacks.

---

## Hardening Best Practices

When deploying Karis-NAS in production:
1. **Local Network Isolation**: Keep Karis-NAS behind a local firewall or access it over a secure VPN (such as Tailscale or WireGuard) rather than exposing port 3251 directly to the public internet without a reverse proxy.
2. **Enable HTTPS / SSL**: Place a TLS reverse proxy (such as Caddy, Nginx, or Cloudflare Tunnels) in front of the server, or place `cert.pem` and `key.pem` in `C:\KarisNAS1.0` for native HTTPS.
3. **Set Strong Administrator Passwords**: Use strong, unique passphrases during initial `/setup`.

---

## Reporting a Vulnerability

If you discover a potential security vulnerability in Karis-NAS, please report it responsibly:

1. **Do not create a public issue** disclosing the vulnerability.
2. Email the maintainer directly or submit a private security advisory on GitHub:
   * **GitHub Security Advisory**: [Report a vulnerability](https://github.com/fanumtalkstech/Karis-NAS/security/advisories)
3. Please include:
   * Description of the vulnerability
   * Steps to reproduce or proof-of-concept (PoC) code
   * Potential impact and affected components

We strive to acknowledge receipt of security reports within 48 hours and release patches in a timely manner.
