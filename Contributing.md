# Contributing to Karis-NAS

Thank you for your interest in improving Karis-NAS! We welcome community contributions, bug reports, and enhancements from developers of all skill levels.

---

## 🛠 Development Setup

1. **Fork and Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/Karis-NAS.git
   cd Karis-NAS
   ```

2. **Create a Python Virtual Environment**:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS / Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Development Server**:
   ```bash
   python app.py
   ```
   The local server will start at `http://localhost:3251`.

---

## 🎨 Design & Coding Guidelines

* **Apple Design System Compliance**:
  * Adhere to macOS Sonoma and iOS Human Interface Guidelines (authentic glassmorphism, SF Pro typography, 24px squircles, and clean touch targets).
  * Ensure new UI components look cohesive across all 17 supported color themes.
* **Clean, Human-Readable Code**:
  * Write clean, standard Python following PEP 8.
  * Avoid excessive boilerplate or robotic comments. Code should be clean, self-documenting, and concise.
* **Windows & Cross-Platform Invariants**:
  * Always use `os.path.join` for file system paths.
  * Ensure file writes remain safe on Windows by utilizing `safe_save_json()` to prevent `[WinError 32]` lock collisions.
  * Support both `C:\KarisNAS1.0` (Windows standard) and POSIX paths.

---

## 🧪 Pre-Submission Testing

Before submitting a Pull Request, verify your changes:

```bash
# 1. Check Python syntax
python -m py_compile app.py installer.py

# 2. Test template rendering
python -c "
import jinja2, glob
env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
for path in glob.glob('templates/*.html'):
    name = path.replace('templates/', '')
    env.get_template(name)
    print(f'Verified: {name}')
"
```

---

## 📬 Submitting Changes

1. Create a feature branch:
   ```bash
   git checkout -b feature/amazing-feature
   ```
2. Commit your changes with a descriptive message:
   ```bash
   git commit -m "feat(player): add repeat button to audio quicklook"
   ```
3. Push to your fork:
   ```bash
   git push origin feature/amazing-feature
   ```
4. Open a **Pull Request** on GitHub against the `main` branch. Provide a clear description of the feature or fix along with screenshots if modifying the UI.
