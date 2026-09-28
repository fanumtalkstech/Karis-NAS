import zipfile
import re
import threading
import urllib.error
import os
import mimetypes
import json
import shutil
import secrets
import psutil
import datetime
import time
import wave
import math
import io
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_from_directory, abort, flash, Response, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix


# Configuration and paths

BASE_DIR = os.environ.get('KARIS_BASE_DIR', r'C:\KarisNAS1.0')
if not os.path.exists(BASE_DIR) and os.path.exists(r'C:\NasDashboard'):
    BASE_DIR = r'C:\NasDashboard'
STORAGE_ROOT = os.path.join(BASE_DIR, 'storage')
USERS_DOCS_ROOT = r'C:\Users\Mason McCarley\Documents'
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
CERT_FILE = os.path.join(BASE_DIR, 'cert.pem')
KEY_FILE = os.path.join(BASE_DIR, 'key.pem')
SECRET_KEY_FILE = os.path.join(BASE_DIR, 'secret.key')
AVATARS_DIR = os.path.join(BASE_DIR, 'avatars')
SHARES_FILE = os.path.join(BASE_DIR, 'shares.json')
SESSIONS_FILE = os.path.join(BASE_DIR, 'sessions.json')
MESSAGES_FILE = os.path.join(BASE_DIR, 'messages.json')
CHAT_ATTACHMENTS_DIR = os.path.join(BASE_DIR, 'chat_attachments')
os.makedirs(CHAT_ATTACHMENTS_DIR, exist_ok=True)

DEFAULT_QUOTA_MB = 51200    # 50 GB default for regular users
ALLOWED_AVATAR_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def human_size(mb):
    """Format a MB value as GB when it's large, MB otherwise."""
    if mb is None:
        return "Unlimited"
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.1f} MB"


EDITABLE_EXTENSIONS = {
    '.txt', '.md', '.json', '.py', '.js', '.html', '.css', '.csv',
    '.yml', '.yaml', '.ini', '.cfg', '.log', '.xml'
}


# Concurrency locks and file persistence

sessions_lock = threading.Lock()
users_lock = threading.Lock()
config_lock = threading.Lock()
shares_lock = threading.Lock()
messages_lock = threading.Lock()
_session_last_touched = {}

def safe_save_json(file_path, data, lock=None):
    """Windows-safe atomic JSON file persistence."""
    if lock:
        with lock:
            _execute_safe_save(file_path, data)
    else:
        _execute_safe_save(file_path, data)

def _execute_safe_save(file_path, data):
    tmp_path = f"{file_path}.tmp_{secrets.token_hex(4)}_{threading.get_ident()}_{int(time.time() * 1000)}"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        max_retries = 8
        for attempt in range(max_retries):
            try:
                os.replace(tmp_path, file_path)
                return
            except (PermissionError, OSError) as e:
                if attempt == max_retries - 1:
                    # Final fallback: direct write to target file
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=4)
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass
                        return
                    except Exception:
                        raise e
                time.sleep(0.02 * (attempt + 1))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(STORAGE_ROOT, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


@app.context_processor
def inject_user_preferences():
    cfg = load_config()
    features = cfg.get('features', {})
    beta_mode = bool(cfg.get('beta_mode', False))
    feature_messaging = bool(features.get('messaging', True)) and beta_mode

    base_ctx = {
        'beta_mode': beta_mode,
        'feature_messaging': feature_messaging,
        'features_config': features,
        'server_config': cfg,
        'weather_zip': cfg.get('weather_zip', '45631'),
        'weather_lat': cfg.get('weather_lat', 38.8098),
        'weather_lon': cfg.get('weather_lon', -82.2104),
        'github_repo': cfg.get('github_repo', 'fanumtalkstech/Karis-NAS'),
        'current_version': cfg.get('current_version', '1.0'),
        'check_github_updates_hourly': cfg.get('check_github_updates_hourly', True),
    }
    if session.get('logged_in'):
        users = load_users()
        info = users.get(session.get('username'), {})
        base_ctx.update({
            'user_theme': info.get('theme', 'dark'),
            'user_widgets': info.get('widgets', {'clock': True, 'weather': True, 'stats': True, 'notes': True, 'messages': True}),
            'user_widget_layout': info.get('widget_layout', {}),
            'user_notes': info.get('notes', ''),
            'user_greeting': info.get('greeting', ''),
            'clock_format': info.get('clock_format', '12h'),
            'weather_location': info.get('weather_location', 'Gallipolis, OH'),
            'current_user_folder': info.get('folder') or cfg.get('storage_folder', USERS_DOCS_ROOT),
        })
    else:
        base_ctx.update({
            'user_theme': 'dark',
            'user_widgets': {'clock': True, 'weather': True, 'stats': True, 'notes': True, 'messages': True},
            'user_widget_layout': {},
            'user_notes': '',
            'user_greeting': '',
            'clock_format': '12h',
            'weather_location': 'Gallipolis, OH',
        })
    return base_ctx


if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(key)
    app.secret_key = key


# Server configuration store

def load_config():
    default_cfg = {
        'demo_mode': False,
        'setup_completed': True,
        'beta_mode': True,
        'storage_folder': USERS_DOCS_ROOT,
        'weather_location': 'Gallipolis, OH',
        'weather_zip': '45631',
        'weather_lat': 38.8098,
        'weather_lon': -82.2104,
        'github_repo': 'fanumtalkstech/Karis-NAS',
        'auto_update_hourly': True,
        'check_github_updates_hourly': True,
        'current_version': '1.0',
        'last_commit_sha': None,
        'features': {
            'messaging': True,
            'system_monitor': True,
            'weather': True,
            'notes': True
        }
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_cfg, f, indent=4)
        return default_cfg
    with open(CONFIG_FILE, 'r') as f:
        try:
            cfg = json.load(f)
            if not isinstance(cfg, dict):
                cfg = default_cfg
            for k, v in default_cfg.items():
                if k not in cfg:
                    cfg[k] = v
            if not isinstance(cfg.get('features'), dict):
                cfg['features'] = default_cfg['features']
            return cfg
        except Exception:
            return default_cfg


def save_config(cfg):
    safe_save_json(CONFIG_FILE, cfg, config_lock)


# Share store

def load_shares():
    if not os.path.exists(SHARES_FILE):
        with open(SHARES_FILE, 'w') as f:
            json.dump([], f, indent=4)
        return []
    with open(SHARES_FILE, 'r') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def save_shares(shares):
    safe_save_json(SHARES_FILE, shares, shares_lock)


# Session management

def load_sessions():
    if not os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, 'w') as f:
            json.dump([], f, indent=4)
        return []
    with open(SESSIONS_FILE, 'r') as f:
        try:
            data = json.load(f)
            if isinstance(data, list):
                return [s for s in data if isinstance(s, dict)]
            elif isinstance(data, dict):
                res = []
                for k, v in data.items():
                    if isinstance(v, dict):
                        if 'id' not in v:
                            v['id'] = k
                        res.append(v)
                return res
            return []
        except Exception:
            return []


def save_sessions(sessions):
    safe_save_json(SESSIONS_FILE, sessions, sessions_lock)


def parse_device_info(ua_string):
    ua = (ua_string or '').lower()
    device = "Desktop PC"
    icon = "💻"
    if "iphone" in ua:
        device = "iPhone"
        icon = "📱"
    elif "ipad" in ua:
        device = "iPad"
        icon = "📱"
    elif "android" in ua:
        device = "Android Phone"
        icon = "📱"
    elif "macintosh" in ua or "mac os" in ua:
        device = "Mac"
        icon = "💻"
    elif "windows" in ua:
        device = "Windows PC"
        icon = "💻"
    elif "linux" in ua:
        device = "Linux Machine"
        icon = "💻"

    browser = "Web Browser"
    if "edg" in ua:
        browser = "Microsoft Edge"
    elif "chrome" in ua and "crios" not in ua:
        browser = "Google Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua or "fxios" in ua:
        browser = "Firefox"

    return f"{device} · {browser}", icon


def register_session(username, user_agent, ip_addr):
    sessions = load_sessions()
    session_token = secrets.token_hex(16)
    device_label, device_icon = parse_device_info(user_agent)
    
    new_sess = {
        'id': session_token,
        'username': username,
        'device': device_label,
        'icon': device_icon,
        'ip': ip_addr or '127.0.0.1',
        'login_time': datetime.datetime.now().strftime('%b %d, %Y at %I:%M %p'),
        'last_active': datetime.datetime.now().strftime('%b %d, %I:%M %p')
    }
    # Keep up to 30 active sessions per user
    user_sessions = [s for s in sessions if s.get('username') == username]
    if len(user_sessions) >= 30:
        oldest = user_sessions[0]
        sessions = [s for s in sessions if s.get('id') != oldest.get('id')]

    sessions.append(new_sess)
    save_sessions(sessions)
    return session_token


def touch_session(session_token):
    if not session_token:
        return
    now_ts = time.time()
    if now_ts - _session_last_touched.get(session_token, 0) < 60:
        return
    _session_last_touched[session_token] = now_ts
    with sessions_lock:
        sessions = load_sessions()
        changed = False
        for s in sessions:
            if s.get('id') == session_token:
                s['last_active'] = datetime.datetime.now().strftime('%b %d, %I:%M %p')
                changed = True
                break
        if changed:
            save_sessions(sessions)


# User store


# Message store

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, 'w') as f:
            json.dump([], f, indent=4)
        return []
    with open(MESSAGES_FILE, 'r') as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []


def save_messages(messages):
    safe_save_json(MESSAGES_FILE, messages, messages_lock)

def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            'ADMIN': {
                'password': generate_password_hash('adminpassword'),
                'role': 'admin', 'folder': None, 'quota_mb': DEFAULT_QUOTA_MB,
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(default_users, f, indent=4)
        return default_users

    with open(USERS_FILE, 'r') as f:
        raw = f.read()
    try:
        users = json.loads(raw)
    except json.JSONDecodeError as e:
        import time
        backup_path = USERS_FILE + f'.broken-{int(time.time())}'
        with open(backup_path, 'w') as bf:
            bf.write(raw)
        raise RuntimeError(
            f'users.json contains invalid JSON ({e}). '
            f'The broken file was saved to {backup_path} for reference - '
            f'fix the syntax error in users.json and restart the app.'
        )

    migrated = False
    for uname, info in users.items():
        pw = info.get('password', '')
        if not pw.startswith(('pbkdf2:', 'scrypt:')):
            info['password'] = generate_password_hash(pw)
            migrated = True
        if 'quota_mb' not in info:
            info['quota_mb'] = DEFAULT_QUOTA_MB
            migrated = True
        if not info.get('folder'):
            info['folder'] = os.path.join(USERS_DOCS_ROOT, secure_filename(uname))
            migrated = True
        if 'theme' not in info:
            info['theme'] = 'dark'
            migrated = True
        if 'widgets' not in info:
            info['widgets'] = {'clock': True, 'weather': True, 'stats': True, 'notes': True}
            migrated = True
        if 'notes' not in info:
            info['notes'] = ''
            migrated = True
        try:
            user_home_folder(uname, info)
        except Exception:
            pass

    if migrated:
        save_users(users)

    return users


def save_users(users):
    safe_save_json(USERS_FILE, users, users_lock)


def migrate_legacy_files(username, target_folder):
    """Transfer files from legacy paths into the user home directory."""
    safe_name = secure_filename(username)
    legacy_sources = [
        os.path.join(STORAGE_ROOT, safe_name),
    ]
    if username.lower() == 'demo':
        legacy_sources.append(DEMO_FOLDER)

    for src_dir in legacy_sources:
        if os.path.exists(src_dir) and os.path.abspath(src_dir) != os.path.abspath(target_folder):
            for item in os.listdir(src_dir):
                src = os.path.join(src_dir, item)
                dst = os.path.join(target_folder, item)
                if not os.path.exists(dst):
                    try:
                        shutil.move(src, dst)
                    except Exception:
                        try:
                            if os.path.isdir(src):
                                shutil.copytree(src, dst)
                            else:
                                shutil.copy2(src, dst)
                        except Exception:
                            pass


def user_home_folder(username, info):
    folder = info.get('folder')
    cfg = load_config()
    cfg_storage = cfg.get('storage_folder')

    if not folder:
        # Check if server config has a storage_folder specified
        if cfg_storage and os.path.exists(cfg_storage):
            if info.get('role') == 'admin':
                folder = cfg_storage
            else:
                folder = os.path.join(cfg_storage, secure_filename(username))
        else:
            folder = os.path.join(USERS_DOCS_ROOT, secure_filename(username))
        info['folder'] = folder
    else:
        # Smart detection for existing files:
        # If an admin's folder is configured as a subfolder (e.g. <parent>/<username>)
        # and that subfolder is empty, BUT the parent directory exists and contains files,
        # adopt the parent directory directly so existing files are immediately discovered!
        if info.get('role') == 'admin' and os.path.isdir(folder):
            try:
                sub_items = os.listdir(folder)
                if len(sub_items) == 0:
                    parent_dir = os.path.dirname(folder)
                    if os.path.isdir(parent_dir) and len(os.listdir(parent_dir)) > 0:
                        if cfg_storage and os.path.abspath(parent_dir) == os.path.abspath(cfg_storage):
                            folder = parent_dir
                            info['folder'] = folder
            except Exception:
                pass

    os.makedirs(folder, exist_ok=True)
    try:
        migrate_legacy_files(username, folder)
    except Exception:
        pass
    return folder


def folder_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


# Demo sandbox


# Auth helpers

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        token = session.get('session_token')
        if token:
            sessions = load_sessions()
            if not any(s.get('id') == token for s in sessions):
                session.clear()
                flash('You have been signed out from this device.', 'error')
                return redirect(url_for('login'))
            touch_session(token)
        return view(*args, **kwargs)
    return wrapped


def get_current_role():
    """Always reads the live role from users.json instead of trusting the session,
    so role changes (promote/demote) take effect immediately, not just after re-login."""
    users = load_users()
    info = users.get(session.get('username'))
    return info.get('role') if info else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if get_current_role() != 'admin':
            return abort(403)
        return view(*args, **kwargs)
    return wrapped


def safe_join(base, *paths):
    base = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *paths))
    if os.path.commonpath([base, target]) != base:
        abort(403)
    return target


def current_home():
    users = load_users()
    info = users.get(session.get('username'))
    if not info:
        session.clear()
        abort(403)
    return user_home_folder(session['username'], info)


def current_quota_mb():
    """Returns the MB cap for the current session, or None for unlimited (admins)."""
    role = get_current_role()
    if role == 'admin':
        return None
    users = load_users()
    info = users.get(session.get('username'), {})
    return info.get('quota_mb', DEFAULT_QUOTA_MB)


# Avatar routes

@app.route('/avatar/<username>')
def avatar(username):
    safe_name = secure_filename(username)
    if os.path.exists(AVATARS_DIR):
        for ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            fname = f"{safe_name}{ext}"
            fpath = os.path.join(AVATARS_DIR, fname)
            if os.path.isfile(fpath):
                return send_from_directory(AVATARS_DIR, fname)

    # Deterministic colorful initials SVG avatar
    colors = [
        ('#007AFF', '#5AC8FA'),
        ('#5856D6', '#AF52DE'),
        ('#34C759', '#30D158'),
        ('#FF9500', '#FFCC00'),
        ('#FF2D55', '#FF375F'),
        ('#32ADE6', '#007AFF'),
        ('#AF52DE', '#FF2D55'),
        ('#30D158', '#007AFF'),
    ]
    color_idx = sum(ord(c) for c in (username or 'U')) % len(colors)
    c1, c2 = colors[color_idx]
    initial = (username[0] if username else '?').upper()

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
        <defs>
            <linearGradient id="grad_{color_idx}" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="{c1}" />
                <stop offset="100%" stop-color="{c2}" />
            </linearGradient>
        </defs>
        <circle cx="50" cy="50" r="50" fill="url(#grad_{color_idx})" />
        <text x="50" y="53" font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, sans-serif"
              font-size="44" font-weight="700" fill="#ffffff" text-anchor="middle" dominant-baseline="central">{initial}</text>
    </svg>"""
    return Response(svg, mimetype='image/svg+xml')


@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():


    file = request.files.get('avatar')
    if not file or not file.filename:
        flash('No file selected for profile picture.', 'error')
        return redirect(url_for('settings'))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        flash('Only PNG, JPG, JPEG, GIF, and WebP images are supported.', 'error')
        return redirect(url_for('settings'))

    username = session['username']
    safe_name = secure_filename(username)
    for old_ext in ALLOWED_AVATAR_EXTENSIONS:
        old_path = os.path.join(AVATARS_DIR, f"{safe_name}{old_ext}")
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    save_path = os.path.join(AVATARS_DIR, f"{safe_name}{ext}")
    file.save(save_path)
    flash('Profile picture updated successfully.', 'success')
    return redirect(url_for('settings'))


@app.route('/remove_avatar', methods=['POST'])
@login_required
def remove_avatar():


    username = session['username']
    safe_name = secure_filename(username)
    removed = False
    for ext in ALLOWED_AVATAR_EXTENSIONS:
        path = os.path.join(AVATARS_DIR, f"{safe_name}{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError:
                pass

    if removed:
        flash('Profile picture reset to default.', 'success')
    return redirect(url_for('settings'))


# Authentication routes

@app.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users = load_users()
        info = users.get(username)
        if info and check_password_hash(info['password'], password):
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session['role'] = info['role']
            user_home_folder(username, info)
            token = register_session(username, request.headers.get('User-Agent', ''), request.remote_addr)
            session['session_token'] = token
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    token = session.get('session_token')
    if token:
        sessions = load_sessions()
        save_sessions([s for s in sessions if s.get('id') != token])
    session.clear()
    return redirect(url_for('login'))


# Dashboard routes

@app.route('/dashboard', defaults={'req_path': ''})
@app.route('/dashboard/<path:req_path>')
@login_required
def dashboard(req_path):
    return _render_dashboard(req_path)


def _render_dashboard(req_path):
    home = current_home()
    abs_path = safe_join(home, req_path)

    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        req_path = ''
        abs_path = home

    all_shares = load_shares()
    current_user = session['username']

    entries = []
    for name in os.listdir(abs_path):
        full = os.path.join(abs_path, name)
        is_dir = os.path.isdir(full)
        entry_rel_path = (req_path + '/' + name).strip('/')

        # Find any active shares for this specific file/folder owned by current user
        item_shares = [
            s for s in all_shares
            if s.get('owner') == current_user and s.get('rel_path') == entry_rel_path
        ]

        entries.append({
            'name': name,
            'is_dir': is_dir,
            'size_kb': None if is_dir else round(os.path.getsize(full) / 1024, 1),
            'editable': (not is_dir) and os.path.splitext(name)[1].lower() in EDITABLE_EXTENSIONS,
            'rel_path': entry_rel_path,
            'is_shared': len(item_shares) > 0,
            'shares': item_shares
        })

    parent_path = os.path.dirname(req_path) if req_path else None

    # Shared with me section
    shared_with_me = []
    users_dict = load_users()
    for s in all_shares:
        if s.get('owner') != current_user:
            if s.get('shared_with') in (current_user, 'everyone'):
                owner = s.get('owner')
                if owner == 'Demo User':
                    o_home = DEMO_FOLDER
                else:
                    o_info = users_dict.get(owner, {})
                    o_home = user_home_folder(owner, o_info)
                item_abs = safe_join(o_home, s.get('rel_path', ''))
                if os.path.exists(item_abs):
                    is_dir = os.path.isdir(item_abs)
                    shared_with_me.append({
                        'id': s.get('id'),
                        'name': s.get('item_name'),
                        'owner': owner,
                        'is_dir': is_dir,
                        'permission': s.get('permission', 'view'),
                        'size_kb': None if is_dir else round(os.path.getsize(item_abs) / 1024, 1),
                        'editable': (not is_dir) and (os.path.splitext(s.get('item_name'))[1].lower() in EDITABLE_EXTENSIONS) and (s.get('permission') == 'edit'),
                        'created_at': s.get('created_at', '')
                    })

    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(home)
        disk_total = round(disk.total / (1024 ** 3), 2)
        disk_used = round(disk.used / (1024 ** 3), 2)
        disk_free = round(disk.free / (1024 ** 3), 2)
        disk_percent = disk.percent
    except Exception:
        disk_total = disk_used = disk_free = disk_percent = 0

    quota_mb = current_quota_mb()
    used_mb = round(folder_size(home) / (1024 * 1024), 1)
    unlimited = quota_mb is None
    quota_percent = 0 if unlimited else min(100, round((used_mb / quota_mb) * 100, 1))

    stats = {
        'cpu': cpu, 'ram_percent': ram.percent,
        'disk_total': disk_total, 'disk_used': disk_used,
        'disk_free': disk_free, 'disk_percent': disk_percent,
        'quota_mb': quota_mb, 'used_mb': used_mb, 'quota_percent': quota_percent,
        'unlimited': unlimited,
        'quota_display': human_size(quota_mb),
        'used_display': human_size(used_mb),
    }

    users = None
    live_role = get_current_role() or session.get('role', 'user')
    if live_role == 'admin':
        users = load_users()
        for uname, info in users.items():
            try:
                info['used_mb'] = round(folder_size(user_home_folder(uname, info)) / (1024 * 1024), 1)
            except Exception:
                info['used_mb'] = 0
            info['used_display'] = human_size(info['used_mb'])
            info['quota_display'] = 'Unlimited' if info.get('role') == 'admin' else human_size(info.get('quota_mb', DEFAULT_QUOTA_MB))

    # Other registered users available to share with
    registered_users = [uname for uname in users_dict.keys() if uname != current_user]

    return render_template(
        'dashboard.html',
        entries=entries, current_path=req_path, parent_path=parent_path,
        stats=stats, username=session['username'], role=live_role,
        users=users,
        shared_with_me=shared_with_me,
        registered_users=registered_users
    )


# Media streaming routes

@app.route('/raw/<path:req_path>')
@login_required
def raw(req_path):
    user = session['username']
    home = current_home()
    abs_path = safe_join(home, req_path)

    if not abs_path or not os.path.isfile(abs_path):
        # Check if accessible via shared file/folder
        shares = load_shares()
        accessible = False
        for s in shares:
            if s.get('shared_with') in (user, 'everyone') or s.get('owner') == user:
                owner_home = get_user_home(s.get('owner'))
                s_path = safe_join(owner_home, s.get('path', ''))
                if s_path and os.path.exists(s_path):
                    if s_path == abs_path or (os.path.isdir(s_path) and abs_path.startswith(s_path)):
                        accessible = True
                        break
        if not accessible or not os.path.isfile(abs_path):
            abort(404)

    file_size = os.path.getsize(abs_path)
    mime_type, _ = mimetypes.guess_type(abs_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    range_header = request.headers.get('Range', None)
    if not range_header:
        resp = send_from_directory(
            os.path.dirname(abs_path),
            os.path.basename(abs_path),
            as_attachment=False,
            mimetype=mime_type
        )
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Content-Length'] = str(file_size)
        return resp

    # HTTP 206 Partial Content for Safari / iOS streaming
    try:
        byte_range = range_header.replace('bytes=', '').strip()
        parts = byte_range.split('-')
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        
        if start >= file_size or end >= file_size or start > end:
            return Response(status=416, headers={'Content-Range': f'bytes */{file_size}'})

        length = end - start + 1
        with open(abs_path, 'rb') as f:
            f.seek(start)
            data = f.read(length)

        resp = Response(data, status=206, mimetype=mime_type)
        resp.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Content-Length'] = str(length)
        return resp
    except Exception:
        resp = send_from_directory(
            os.path.dirname(abs_path),
            os.path.basename(abs_path),
            as_attachment=False,
            mimetype=mime_type
        )
        resp.headers['Accept-Ranges'] = 'bytes'
        return resp


@app.route('/download/<path:req_path>')
@login_required
def download(req_path):
    home = current_home()
    abs_path = safe_join(home, req_path)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path), as_attachment=True)


@app.route('/upload', methods=['POST'], endpoint='upload')
@app.route('/upload_file', methods=['POST'], endpoint='upload_file')
@login_required
def upload():
    home = current_home()
    current_path = request.form.get('current_path', '')
    target_dir = safe_join(home, current_path)

    # Multi-file and drag-and-drop support
    files = request.files.getlist('files')
    if not files or (len(files) == 1 and not files[0].filename):
        single_file = request.files.get('file')
        files = [single_file] if single_file and single_file.filename else []

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not files:
        if is_ajax:
            return jsonify({'success': False, 'error': 'No files received.'}), 400
        flash('No files selected for upload.', 'error')
        return redirect(url_for('dashboard', req_path=current_path))

    saved_count = 0
    quota_mb = current_quota_mb()

    for file in files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        if not filename:
            continue
        dest = os.path.join(target_dir, filename)
        file.save(dest)
        if quota_mb is not None and folder_size(home) > quota_mb * 1024 * 1024:
            try:
                os.remove(dest)
            except OSError:
                pass
            msg = f'Upload stopped: "{filename}" exceeds your {quota_mb} MB storage quota.'
            if is_ajax:
                return jsonify({'success': False, 'error': msg}), 400
            flash(msg, 'error')
            break
        else:
            saved_count += 1

    if saved_count > 0:
        msg = f'{saved_count} file{"s" if saved_count > 1 else ""} uploaded successfully.'
        if is_ajax:
            return jsonify({'success': True, 'count': saved_count, 'message': msg})
        flash(msg, 'success')

    return redirect(url_for('dashboard', req_path=current_path))


@app.route('/create_folder', methods=['POST'], endpoint='create_folder')
@app.route('/new_folder', methods=['POST'], endpoint='new_folder')
@login_required
def create_folder():
    home = current_home()
    current_path = request.form.get('current_path', '')
    folder_name = secure_filename(request.form.get('folder_name', ''))
    if folder_name:
        target_dir = safe_join(home, current_path)
        os.makedirs(os.path.join(target_dir, folder_name), exist_ok=True)
        flash(f'Folder "{folder_name}" created.', 'success')
    return redirect(url_for('dashboard', req_path=current_path))


@app.route('/delete/<path:req_path>', methods=['POST'])
@login_required
def delete(req_path):
    home = current_home()
    abs_path = safe_join(home, req_path)
    current_path = os.path.dirname(req_path)

    # Also clean up any shares associated with this item
    shares = load_shares()
    new_shares = [
        s for s in shares
        if not (s.get('owner') == session['username'] and s.get('rel_path') == req_path)
    ]
    if len(new_shares) != len(shares):
        save_shares(new_shares)

    if os.path.isdir(abs_path):
        try:
            os.rmdir(abs_path)
            flash('Folder deleted.', 'success')
        except OSError:
            flash('Folder must be empty before deleting.', 'error')
    elif os.path.isfile(abs_path):
        os.remove(abs_path)
        flash('File deleted.', 'success')

    return redirect(url_for('dashboard', req_path=current_path))


@app.route('/edit/<path:req_path>', methods=['GET', 'POST'])
@login_required
def edit(req_path):
    home = current_home()
    abs_path = safe_join(home, req_path)

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in EDITABLE_EXTENSIONS:
        abort(403)

    if request.method == 'POST':
        content = request.form.get('content', '')
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        flash('File saved successfully.', 'success')
        return redirect(url_for('dashboard', req_path=os.path.dirname(req_path)))

    if not os.path.isfile(abs_path):
        abort(404)
    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    return render_template('edit.html', filename=req_path, content=content)


# File sharing routes

@app.route('/share', methods=['POST'])
@login_required
def share_item():
    rel_path = request.form.get('rel_path', '').strip()
    target_user = request.form.get('target_user', '').strip()
    permission = request.form.get('permission', 'view').strip()  # 'view' or 'edit'

    if not rel_path or not target_user:
        flash('Please select a file and a user to share with.', 'error')
        return redirect(url_for('dashboard'))

    home = current_home()
    abs_path = safe_join(home, rel_path)
    if not os.path.exists(abs_path):
        flash('Selected item no longer exists.', 'error')
        return redirect(url_for('dashboard'))

    current_user = session['username']
    if target_user == current_user:
        flash("You cannot share an item with yourself.", 'error')
        return redirect(url_for('dashboard', req_path=os.path.dirname(rel_path)))

    users = load_users()
    if target_user != 'everyone' and target_user not in users:
        flash(f'User "{target_user}" was not found.', 'error')
        return redirect(url_for('dashboard', req_path=os.path.dirname(rel_path)))

    shares = load_shares()
    item_name = os.path.basename(rel_path)

    # Check if a share for this item and user already exists -> update permission
    for s in shares:
        if (s.get('owner') == current_user and
            s.get('rel_path') == rel_path and
            s.get('shared_with') == target_user):
            s['permission'] = permission
            save_shares(shares)
            flash(f'Updated permissions for {target_user} to "{permission}".', 'success')
            return redirect(url_for('dashboard', req_path=os.path.dirname(rel_path)))

    new_share = {
        'id': secrets.token_hex(8),
        'owner': current_user,
        'shared_with': target_user,
        'rel_path': rel_path,
        'item_name': item_name,
        'is_dir': os.path.isdir(abs_path),
        'permission': permission,
        'created_at': datetime.datetime.now().strftime('%b %d, %Y')
    }
    shares.append(new_share)
    save_shares(shares)

    target_desc = 'everyone' if target_user == 'everyone' else target_user
    flash(f'Shared "{item_name}" with {target_desc} ({permission}).', 'success')
    return redirect(url_for('dashboard', req_path=os.path.dirname(rel_path)))


@app.route('/unshare/<share_id>', methods=['POST'])
@login_required
def unshare_item(share_id):
    shares = load_shares()
    current_user = session['username']
    live_role = get_current_role() or session.get('role', 'user')

    updated = [
        s for s in shares
        if not (s.get('id') == share_id and (s.get('owner') == current_user or live_role == 'admin'))
    ]

    if len(updated) < len(shares):
        save_shares(updated)
        flash('Sharing revoked.', 'success')
    else:
        flash('Could not remove share (unauthorized or not found).', 'error')

    return redirect(url_for('dashboard'))


@app.route('/shared/download/<share_id>')
@login_required
def shared_download(share_id):
    shares = load_shares()
    share = next((s for s in shares if s.get('id') == share_id), None)
    if not share:
        abort(404)

    current_user = session['username']
    live_role = get_current_role() or session.get('role', 'user')
    if not (share['shared_with'] in (current_user, 'everyone') or
            share['owner'] == current_user or live_role == 'admin'):
        abort(403)

    users = load_users()
    owner = share['owner']
    if owner == 'Demo User':
        owner_home = DEMO_FOLDER
    else:
        owner_info = users.get(owner)
        if not owner_info:
            abort(404)
        owner_home = user_home_folder(owner, owner_info)

    abs_path = safe_join(owner_home, share['rel_path'])
    if not os.path.isfile(abs_path):
        abort(404)

    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path), as_attachment=True)


@app.route('/shared/edit/<share_id>', methods=['GET', 'POST'])
@login_required
def shared_edit(share_id):
    shares = load_shares()
    share = next((s for s in shares if s.get('id') == share_id), None)
    if not share:
        abort(404)

    current_user = session['username']
    live_role = get_current_role() or session.get('role', 'user')
    if not (share['shared_with'] in (current_user, 'everyone') or
            share['owner'] == current_user or live_role == 'admin'):
        abort(403)

    if share.get('permission') != 'edit' and share['owner'] != current_user and live_role != 'admin':
        abort(403)

    users = load_users()
    owner = share['owner']
    if owner == 'Demo User':
        owner_home = DEMO_FOLDER
    else:
        owner_info = users.get(owner)
        if not owner_info:
            abort(404)
        owner_home = user_home_folder(owner, owner_info)

    abs_path = safe_join(owner_home, share['rel_path'])
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in EDITABLE_EXTENSIONS:
        abort(403)

    if request.method == 'POST':
        content = request.form.get('content', '')
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        flash(f'Saved changes to "{share["item_name"]}".', 'success')
        return redirect(url_for('dashboard'))

    if not os.path.isfile(abs_path):
        abort(404)

    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    return render_template('edit.html', filename=f"{share['item_name']} (shared by {owner})", content=content)


# Settings (change password & profile picture)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    message = None
    error = None

    if request.method == 'POST':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            users = load_users()
            info = users[session['username']]

            if not check_password_hash(info['password'], current_password):
                error = 'Current password is incorrect.'
            elif len(new_password) < 4:
                error = 'New password must be at least 4 characters.'
            else:
                info['password'] = generate_password_hash(new_password)
                save_users(users)
                message = 'Password updated successfully.'

    all_sess = load_sessions()
    user_sessions = [s for s in all_sess if s.get('username') == session['username']]
    user = session['username']
    users = load_users()
    info = users.get(user, {})
    user_folder = user_home_folder(user, info)
    cfg = load_config()

    return render_template(
        'settings.html',
        current_user=user,
        username=user,
        role=get_current_role() or session.get('role', 'user'),
        message=message,
        error=error,
        user_sessions=user_sessions,
        active_sessions=user_sessions,
        current_token=session.get('session_token'),
        current_session_token=session.get('session_token'),
        user_folder=user_folder,
        storage_folder=user_folder,
        users=users,
        server_config=cfg
    )


# User administration

@app.route('/admin/add_user', methods=['POST'])
@admin_required
def add_user():
    new_username = request.form.get('new_username', '').strip()
    new_password = request.form.get('new_password', '').strip()
    new_role = request.form.get('new_role', 'user')
    quota_gb = request.form.get('quota_gb', '50')

    if new_username and new_password and new_role in ('user', 'admin'):
        users = load_users()
        if new_username not in users:
            try:
                quota_val = max(1, int(round(float(quota_gb) * 1024)))
            except ValueError:
                quota_val = DEFAULT_QUOTA_MB
            user_folder = os.path.join(USERS_DOCS_ROOT, secure_filename(new_username))
            os.makedirs(user_folder, exist_ok=True)
            users[new_username] = {
                'password': generate_password_hash(new_password),
                'role': new_role,
                'folder': user_folder,
                'quota_mb': quota_val,
            }
            save_users(users)
            user_home_folder(new_username, users[new_username])
            flash(f'User "{new_username}" created.', 'success')
        else:
            flash('That username already exists.', 'error')

    return redirect(url_for('dashboard'))


@app.route('/admin/update_user/<username>', methods=['POST'])
@admin_required
def update_user(username):
    users = load_users()
    if username not in users:
        abort(404)

    action = request.form.get('action')

    if action == 'role':
        if username == session['username']:
            flash("You can't change your own role.", 'error')
        else:
            new_role = request.form.get('role')
            if new_role in ('user', 'admin'):
                users[username]['role'] = new_role
                save_users(users)
                flash(f'Role updated for {username}.', 'success')

    elif action == 'quota':
        try:
            quota_gb = float(request.form.get('quota_gb', ''))
            users[username]['quota_mb'] = max(1, int(round(quota_gb * 1024)))
            save_users(users)
            flash(f'Storage limit updated for {username}.', 'success')
        except (ValueError, TypeError):
            flash('Enter a valid number of GB for the storage limit.', 'error')

    elif action == 'password':
        new_password = request.form.get('new_password', '')
        if len(new_password) < 4:
            flash('New password must be at least 4 characters.', 'error')
        else:
            users[username]['password'] = generate_password_hash(new_password)
            save_users(users)
            flash(f'Password reset for {username}.', 'success')

    return redirect(url_for('dashboard'))


@app.route('/admin/delete_user/<username>', methods=['POST'])
@admin_required
def delete_user(username):
    if username == session['username']:
        flash("You can't delete your own account.", 'error')
        return redirect(url_for('dashboard'))

    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        flash(f'User "{username}" deleted. Their files were left on disk.', 'success')
    return redirect(url_for('dashboard'))


# Storage Folder Management & Discovery APIs

@app.route('/settings/update_storage_folder', methods=['POST'])
@login_required
def update_storage_folder():
    """Allows user or admin to update their active physical folder path on disk."""
    raw_folder = request.form.get('storage_folder', '').strip()
    if not raw_folder:
        flash('Storage path cannot be empty.', 'error')
        return redirect(url_for('settings') + '#general')

    target_dir = os.path.abspath(os.path.expanduser(raw_folder))

    # Validate directory
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        flash(f'Could not create or access directory "{target_dir}": {e}', 'error')
        return redirect(url_for('settings') + '#general')

    # Test write permissions with a probe file
    probe_file = os.path.join(target_dir, f'.karis_probe_{secrets.token_hex(4)}')
    try:
        with open(probe_file, 'w') as f:
            f.write('ok')
        os.remove(probe_file)
    except Exception as e:
        flash(f'Directory "{target_dir}" is not writable: {e}', 'error')
        return redirect(url_for('settings') + '#general')

    # Count discovered files & directories
    try:
        items = os.listdir(target_dir)
        file_count = sum(1 for item in items if os.path.isfile(os.path.join(target_dir, item)))
        dir_count = sum(1 for item in items if os.path.isdir(os.path.join(target_dir, item)))
    except Exception:
        file_count = dir_count = 0

    current_user = session['username']
    users = load_users()
    if current_user in users:
        users[current_user]['folder'] = target_dir
        save_users(users)

    # If admin, also update global server storage_folder setting
    if get_current_role() == 'admin':
        cfg = load_config()
        cfg['storage_folder'] = target_dir
        save_config(cfg)

    flash(
        f'✓ Active storage folder updated to "{target_dir}". '
        f'Discovered {file_count} files and {dir_count} subfolders — all are now accessible on your Dashboard.',
        'success'
    )
    return redirect(url_for('settings') + '#general')


@app.route('/api/storage/scan_folder', methods=['POST'])
@login_required
def api_storage_scan_folder():
    """AJAX endpoint taking a folder path, testing accessibility, and returning item count and size."""
    data = request.get_json(silent=True) or request.form
    raw_path = (data.get('folder_path') or '').strip()

    if not raw_path:
        return jsonify({'success': False, 'error': 'No folder path provided'}), 400

    target_path = os.path.abspath(os.path.expanduser(raw_path))

    if not os.path.exists(target_path):
        return jsonify({
            'success': True,
            'exists': False,
            'readable': False,
            'writable': False,
            'formatted_path': target_path,
            'message': 'Folder does not exist yet (will be created automatically if selected).'
        })

    if not os.path.isdir(target_path):
        return jsonify({
            'success': False,
            'exists': True,
            'error': 'Specified path is a file, not a directory.'
        }), 400

    readable = os.access(target_path, os.R_OK)

    # Test write permissions
    writable = False
    probe_file = os.path.join(target_path, f'.karis_probe_{secrets.token_hex(4)}')
    try:
        with open(probe_file, 'w') as f:
            f.write('probe')
        os.remove(probe_file)
        writable = True
    except Exception:
        writable = False

    files = 0
    dirs = 0
    total_bytes = 0
    sample_items = []

    try:
        for entry in os.scandir(target_path):
            try:
                if entry.is_file(follow_symlinks=False):
                    files += 1
                    total_bytes += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    dirs += 1
                if len(sample_items) < 8:
                    sample_items.append(entry.name)
            except OSError:
                pass
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Permission or I/O error reading directory: {e}'
        }), 500

    total_mb = round(total_bytes / (1024 * 1024), 1)

    return jsonify({
        'success': True,
        'exists': True,
        'readable': readable,
        'writable': writable,
        'file_count': files,
        'dir_count': dirs,
        'total_items': files + dirs,
        'total_size_bytes': total_bytes,
        'total_size_display': human_size(total_mb),
        'sample_items': sample_items,
        'formatted_path': target_path
    })


# Global Error Handling & Diagnostic Reporting

def build_error_report(exc):
    import traceback
    import platform

    tb_text = traceback.format_exc()
    try:
        user = session.get('username', '(not logged in)')
        role = session.get('role', '-')
    except Exception:
        user, role = '(unknown)', '-'

    lines = [
        "Karis-NAS System Diagnostic Report",
        "=" * 48,
        f"Time:        {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"URL:         {request.method} {request.path}",
        f"User:        {user} (Role: {role})",
        f"Platform:    {platform.system()} {platform.release()} (Python {platform.python_version()})",
        f"Exception:   {type(exc).__name__}: {exc}",
        "",
        "Stack Traceback:",
        "-" * 48,
        tb_text.strip(),
    ]
    return "\n".join(lines)


@app.errorhandler(400)
def handle_bad_request(e):
    return render_template(
        'error.html',
        status_code=400,
        error_title="Bad Request",
        error_type="BadRequest",
        error_summary="The server could not understand or process your request.",
        what_happened="The request format was invalid or contained corrupted data parameters.",
        why_happened=str(e),
        how_to_fix="Verify your form inputs or refresh the page and try again.",
        report=None
    ), 400


@app.errorhandler(403)
def handle_forbidden(e):
    return render_template(
        'error.html',
        status_code=403,
        error_title="Access Forbidden",
        error_type="PermissionDenied",
        error_summary="You do not have permission to access this item.",
        what_happened="This area or resource requires elevated administrator privileges or shared access.",
        why_happened="Your current user account is not authorized to view or modify this resource.",
        how_to_fix="Sign in with an administrator account or ask the owner to share this item with you.",
        report=None
    ), 403


@app.errorhandler(404)
def handle_not_found(e):
    return render_template(
        'error.html',
        status_code=404,
        error_title="Page or Resource Not Found",
        error_type="NotFound",
        error_summary="The requested path could not be located on this Karis-NAS server.",
        what_happened="The link you followed may be incorrect, or the file or folder was deleted or moved.",
        why_happened="No route or storage resource matches the requested URL.",
        how_to_fix="Verify the path or return to your dashboard.",
        report=None
    ), 404


@app.errorhandler(Exception)
def handle_any_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        # Allow standard HTTP exceptions with specific status codes to be styled
        if e.code in (400, 403, 404):
            return e

    import traceback
    traceback.print_exc()
    report_text = build_error_report(e)

    # Safe render with emergency inline HTML fallback if error.html ever fails
    try:
        return render_template(
            'error.html',
            status_code=500,
            error_title="Internal Application Error",
            error_type=type(e).__name__,
            error_summary=str(e) or "An unhandled exception occurred.",
            what_happened="The server encountered an unexpected error while processing your request.",
            why_happened=f"{type(e).__name__}: {str(e)}",
            how_to_fix="Review the diagnostic report below, return to the dashboard, or report this issue on GitHub.",
            report=report_text
        ), 500
    except Exception as fallback_err:
        fallback_html = f"""<!DOCTYPE html>
<html>
<head><title>500 System Error | Karis-NAS</title></head>
<body style="font-family:-apple-system,system-ui,sans-serif;background:#0A0A0C;color:#F5F5F7;padding:32px;">
    <div style="max-width:640px;margin:40px auto;background:#1C1C1E;padding:32px;border-radius:24px;border:1px solid #333;">
        <h2 style="color:#FF453A;margin-top:0;">⚠️ 500 Internal Error</h2>
        <p><strong>{type(e).__name__}:</strong> {e}</p>
        <pre style="background:#000;padding:16px;border-radius:12px;overflow:auto;font-size:12px;">{report_text}</pre>
        <p><a href="/dashboard" style="color:#0A84FF;text-decoration:none;font-weight:600;">← Back to Dashboard</a></p>
    </div>
</body>
</html>"""
        return Response(fallback_html, status=500, mimetype='text/html')


# PWA routes

@app.route('/manifest.json')
def manifest():
    pwa_data = {
        "name": "NAS Portal",
        "short_name": "NAS",
        "description": "Personal NAS Dashboard & Cloud Storage",
        "start_url": "/dashboard",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#121214",
        "theme_color": "#007AFF",
        "icons": [
            {
                "src": url_for('app_icon'),
                "sizes": "192x192 512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    }
    return Response(json.dumps(pwa_data, indent=2), mimetype='application/manifest+json')


@app.route('/app_icon')
def app_icon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
        <defs>
            <linearGradient id="iconGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#007AFF" />
                <stop offset="100%" stop-color="#5856D6" />
            </linearGradient>
        </defs>
        <rect width="512" height="512" rx="115" fill="url(#iconGrad)"/>
        <rect x="96" y="110" width="320" height="292" rx="24" fill="#1C1C1E" stroke="#38383A" stroke-width="4"/>
        <rect x="126" y="146" width="260" height="52" rx="10" fill="#2C2C2E"/>
        <circle cx="152" cy="172" r="7" fill="#30D158"/>
        <rect x="176" y="168" width="160" height="8" rx="4" fill="#48484A"/>
        <rect x="126" y="214" width="260" height="52" rx="10" fill="#2C2C2E"/>
        <circle cx="152" cy="240" r="7" fill="#0A84FF"/>
        <rect x="176" y="236" width="180" height="8" rx="4" fill="#48484A"/>
        <rect x="126" y="282" width="260" height="52" rx="10" fill="#2C2C2E"/>
        <circle cx="152" cy="308" r="7" fill="#30D158"/>
        <rect x="176" y="304" width="140" height="8" rx="4" fill="#48484A"/>
        <rect x="126" y="354" width="260" height="24" rx="6" fill="#141416"/>
        <circle cx="360" cy="366" r="5" fill="#34C759"/>
    </svg>"""
    return Response(svg, mimetype='image/svg+xml')


# Theme & Widget personalization routes

@app.route('/set_theme', methods=['POST'])
@login_required
def set_theme():
    data = request.get_json(silent=True) or request.form
    theme = (data.get('theme') or 'dark').strip().lower()
    allowed_themes = {'dark', 'oled', 'sunset', 'ocean', 'nord', 'emerald', 'cyberpunk', 'rose', 'mocha', 'light', 'system'}
    if theme in allowed_themes:
        users = load_users()
        username = session['username']
        if username in users:
            users[username]['theme'] = theme
            save_users(users)
            session['theme'] = theme
            return jsonify({'success': True, 'theme': theme})
    return jsonify({'success': False, 'error': 'Invalid theme'}), 400


@app.route('/set_widgets', methods=['POST'])
@login_required
def set_widgets():
    data = request.get_json(silent=True) or request.form
    users = load_users()
    username = session['username']
    if username in users:
        if 'layout' in data:
            users[username]['widget_layout'] = data.get('layout')
        current_w = users[username].get('widgets', {})
        for key in ('clock', 'weather', 'stats', 'notes', 'messages'):
            if key in data:
                val = data.get(key)
                if isinstance(val, str):
                    current_w[key] = val.lower() in ('true', '1', 'on')
                else:
                    current_w[key] = bool(val)
        users[username]['widgets'] = current_w
        save_users(users)
        return jsonify({'success': True, 'widgets': current_w, 'layout': users[username].get('widget_layout')})
    return jsonify({'success': False, 'error': 'User not found'}), 404


@app.route('/save_notes', methods=['POST'])
@login_required
def save_notes():
    data = request.get_json(silent=True) or request.form
    notes = data.get('notes', '')
    users = load_users()
    username = session['username']
    if username in users:
        users[username]['notes'] = notes[:10000]
        save_users(users)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'User not found'}), 404


# Session Management routes

@app.route('/revoke_session/<session_id>', methods=['POST'])
@login_required
def revoke_session(session_id):
    username = session['username']
    sessions = load_sessions()
    updated = [s for s in sessions if not (s.get('id') == session_id and s.get('username') == username)]
    if len(updated) < len(sessions):
        save_sessions(updated)
        flash('Device signed out.', 'success')
    return redirect(url_for('settings'))


@app.route('/revoke_other_sessions', methods=['POST'])
@login_required
def revoke_other_sessions():
    username = session['username']
    current_token = session.get('session_token')
    sessions = load_sessions()
    updated = [s for s in sessions if s.get('username') != username or s.get('id') == current_token]
    save_sessions(updated)
    flash('All other devices have been signed out.', 'success')
    return redirect(url_for('settings'))


# Live Real-time System Monitor API

@app.route('/api/system_stats')
@login_required
def api_system_stats():
    home = current_home()
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()

    try:
        disk = psutil.disk_usage(home)
        disk_total = round(disk.total / (1024 ** 3), 2)
        disk_used = round(disk.used / (1024 ** 3), 2)
        disk_free = round(disk.free / (1024 ** 3), 2)
        disk_percent = disk.percent
    except Exception:
        disk_total = disk_used = disk_free = disk_percent = 0

    quota_mb = current_quota_mb()
    used_bytes = folder_size(home)
    used_mb = round(used_bytes / (1024 * 1024), 1)
    unlimited = quota_mb is None
    quota_percent = 0 if unlimited else min(100, round((used_mb / quota_mb) * 100, 1))

    try:
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_delta = datetime.datetime.now() - boot_time
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        mins, _ = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {mins}m" if days > 0 else f"{hours}h {mins}m"
    except Exception:
        uptime_str = "Active"

    users = load_users()
    user_theme = users.get(session.get('username'), {}).get('theme', 'dark')

    return jsonify({
        'cpu': cpu,
        'ram_percent': ram.percent,
        'ram_used_gb': round(ram.used / (1024 ** 3), 2),
        'ram_total_gb': round(ram.total / (1024 ** 3), 2),
        'disk_total': disk_total,
        'disk_used': disk_used,
        'disk_free': disk_free,
        'disk_percent': disk_percent,
        'quota_mb': quota_mb,
        'used_mb': used_mb,
        'quota_percent': quota_percent,
        'unlimited': unlimited,
        'used_display': human_size(used_mb),
        'quota_display': human_size(quota_mb),
        'uptime': uptime_str,
        'theme': user_theme,
    })


@app.route('/set_homescreen_pref', methods=['POST'])
@login_required
def set_homescreen_pref():
    data = request.get_json(silent=True) or request.form
    users = load_users()
    username = session['username']
    if username in users:
        if 'greeting' in data:
            users[username]['greeting'] = data.get('greeting', '').strip()[:60]
        if 'clock_format' in data:
            users[username]['clock_format'] = '24h' if data.get('clock_format') == '24h' else '12h'
        if 'weather_location' in data:
            users[username]['weather_location'] = data.get('weather_location', '').strip()[:60]
        save_users(users)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'User not found'}), 404


# Setup wizard

@app.before_request
def check_first_run():
    # Ignore static assets, manifest, icons, and setup itself
    exempt_prefixes = ('/setup', '/static', '/manifest.json', '/app_icon')
    if any(request.path.startswith(p) for p in exempt_prefixes):
        return None
    cfg = load_config()
    users = load_users()
    if not cfg.get('setup_completed', False) or len(users) == 0:
        return redirect(url_for('setup'))
    return None


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    cfg = load_config()
    users = load_users()
    # If setup is already completed and we have an active admin session, allow access; otherwise redirect to login
    if cfg.get('setup_completed', False) and len(users) > 0:
        if not session.get('logged_in') or get_current_role() != 'admin':
            return redirect(url_for('login'))

    if request.method == 'POST':
        admin_user = request.form.get('admin_username', '').strip()
        admin_pass = request.form.get('admin_password', '')
        storage_dir = request.form.get('storage_folder', '').strip() or USERS_DOCS_ROOT
        feature_msg = request.form.get('feature_messaging') is not None
        beta_mode = request.form.get('beta_mode') is not None
        feature_stats = request.form.get('feature_stats') is not None
        add_users_raw = request.form.get('additional_users_json', '[]')

        if not admin_user or not admin_pass:
            flash('Administrator username and password are required.', 'error')
            return render_template('setup.html')

        # Update users
        existing_users = load_users()
        # Smart Folder Mapping for Primary Administrator:
        # If storage_dir exists and already has files/folders (or user explicitly selected it),
        # map admin directly to storage_dir so all existing files are immediately visible!
        admin_folder = storage_dir
        os.makedirs(admin_folder, exist_ok=True)

        existing_users[admin_user] = {
            'password': generate_password_hash(admin_pass),
            'role': 'admin',
            'folder': admin_folder,
            'quota_mb': DEFAULT_QUOTA_MB,
            'theme': 'dark',
            'widgets': {'clock': True, 'weather': True, 'stats': feature_stats, 'notes': True},
            'notes': '',
            'greeting': f"Welcome, {admin_user}"
        }

        # Parse additional users
        try:
            additional_users = json.loads(add_users_raw)
            for u in additional_users:
                uname = u.get('username', '').strip()
                upass = u.get('password', '')
                uquota = int(u.get('quota_gb', 50)) * 1024
                if uname and upass:
                    existing_users[uname] = {
                        'password': generate_password_hash(upass),
                        'role': 'user',
                        'folder': os.path.join(storage_dir, secure_filename(uname)),
                        'quota_mb': uquota,
                        'theme': 'dark',
                        'widgets': {'clock': True, 'weather': True, 'stats': feature_stats, 'notes': True},
                        'notes': '',
                        'greeting': f"Welcome, {uname}"
                    }
        except Exception:
            pass

        save_users(existing_users)

        # Update config
        weather_zip = request.form.get('weather_zip', '45631').strip() or '45631'
        weather_loc = request.form.get('weather_location', 'Gallipolis, OH').strip() or 'Gallipolis, OH'
        try:
            weather_lat = float(request.form.get('weather_lat', 38.8098))
            weather_lon = float(request.form.get('weather_lon', -82.2104))
        except Exception:
            weather_lat, weather_lon = 38.8098, -82.2104

        cfg['setup_completed'] = True
        cfg['beta_mode'] = beta_mode
        cfg['storage_folder'] = storage_dir
        cfg['weather_zip'] = weather_zip
        cfg['weather_location'] = weather_loc
        cfg['weather_lat'] = weather_lat
        cfg['weather_lon'] = weather_lon
        cfg['features'] = {
            'messaging': feature_msg,
            'system_monitor': feature_stats,
            'weather': True,
            'notes': True
        }
        save_config(cfg)

        # Auto-login the admin
        session.clear()
        session['logged_in'] = True
        session['username'] = admin_user
        session['role'] = 'admin'
        token = register_session(admin_user, request.headers.get('User-Agent', ''), request.remote_addr)
        session['session_token'] = token

        flash('Setup completed successfully! Welcome to NAS Portal.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('setup.html')


# Factory Reset & Setup Rerun

@app.route('/admin/factory_reset', methods=['POST'])
@login_required
def admin_factory_reset():
    if get_current_role() != 'admin':
        abort(403)
    cfg = load_config()
    cfg['setup_completed'] = False
    save_config(cfg)
    save_sessions([])
    session.clear()
    flash('Server has been factory reset. Welcome to the Setup Wizard!', 'success')
    return redirect(url_for('setup'))


# Zipcode Geocoding Lookup for Weather

@app.route('/api/lookup_zipcode/<zipcode>')
def api_lookup_zipcode(zipcode):
    clean_zip = ''.join(c for c in zipcode if c.isdigit())[:5]
    if not clean_zip:
        return jsonify({'success': False, 'error': 'Invalid zipcode'}), 400

    # Fast offline fallback for Gallipolis, OH
    if clean_zip == '45631':
        return jsonify({
            'success': True, 'location': 'Gallipolis, OH',
            'lat': 38.8098, 'lon': -82.2104, 'zip': clean_zip
        })

    # Online lookup via open zippopotam.us
    try:
        import urllib.request
        req = urllib.request.Request(
            f'https://api.zippopotam.us/us/{clean_zip}',
            headers={'User-Agent': 'NasPortal/1.0'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            place = data['places'][0]
            city = place['place name']
            state = place['state abbreviation']
            lat = float(place['latitude'])
            lon = float(place['longitude'])
            return jsonify({
                'success': True,
                'location': f"{city}, {state}",
                'lat': lat,
                'lon': lon,
                'zip': clean_zip
            })
    except Exception:
        # Default to Gallipolis fallback if network lookup fails
        return jsonify({
            'success': True, 'location': f'ZIP {clean_zip} (Default)',
            'lat': 38.8098, 'lon': -82.2104, 'zip': clean_zip
        })


# Admin Optional & Beta Feature Toggles

@app.route('/admin/update_features', methods=['POST'])
@login_required
def admin_update_features():
    if get_current_role() != 'admin':
        abort(403)

    cfg = load_config()
    cfg['beta_mode'] = request.form.get('beta_mode') is not None

    if 'features' not in cfg:
        cfg['features'] = {}

    cfg['features']['messaging'] = request.form.get('feature_messaging') is not None
    cfg['features']['system_monitor'] = request.form.get('feature_system_monitor') is not None
    cfg['features']['weather'] = request.form.get('feature_weather') is not None
    cfg['features']['notes'] = request.form.get('feature_notes') is not None

    save_config(cfg)
    flash('Feature flags and Beta settings updated successfully.', 'success')
    return redirect(url_for('settings') + '#optional_features')


# End-to-End Encrypted (E2EE) Messaging APIs

messages_lock = threading.Lock()


@app.route('/api/messages/conversations')
@login_required
def api_message_conversations():
    cfg = load_config()
    if cfg.get('features', {}).get('messaging') is False:
        return jsonify({'error': 'Messaging is disabled'}), 403

    current_user = session['username']
    users = load_users()
    messages = load_messages()

    convos = []
    for uname, uinfo in users.items():
        if uname == current_user:
            continue

        user_msgs = [
            m for m in messages
            if (m.get('sender') == current_user and m.get('recipient') == uname)
            or (m.get('sender') == uname and m.get('recipient') == current_user)
        ]
        user_msgs.sort(key=lambda x: x.get('timestamp', ''))

        # Only count unread non-deleted messages received by current_user
        unread_count = sum(
            1 for m in user_msgs
            if m.get('recipient') == current_user and not m.get('read', False) and not m.get('deleted', False)
        )

        last_msg = user_msgs[-1] if user_msgs else None
        last_time = last_msg.get('display_time', '') if last_msg else ''

        convos.append({
            'username': uname,
            'role': uinfo.get('role', 'user'),
            'unread': unread_count,
            'last_time': last_time,
            'has_messages': len(user_msgs) > 0
        })

    return jsonify({'conversations': convos})


@app.route('/api/messages/get/<recipient>')
@login_required
def api_messages_get(recipient):
    cfg = load_config()
    if cfg.get('features', {}).get('messaging') is False:
        return jsonify({'error': 'Messaging is disabled'}), 403

    current_user = session['username']
    messages = load_messages()

    convo_msgs = [
        m for m in messages
        if (m.get('sender') == current_user and m.get('recipient') == recipient)
        or (m.get('sender') == recipient and m.get('recipient') == current_user)
    ]
    convo_msgs.sort(key=lambda x: x.get('timestamp', ''))

    # Mark received as read (thread-safe)
    changed = False
    with messages_lock:
        for m in convo_msgs:
            if m.get('recipient') == current_user and not m.get('read', False) and not m.get('deleted', False):
                m['read'] = True
                changed = True
        if changed:
            save_messages(messages)

    # Return message objects including id, sender, recipient, ciphertext, iv, timestamp, display_time, read, reactions, deleted, reply_to
    formatted_msgs = []
    for m in convo_msgs:
        is_deleted = bool(m.get('deleted', False))
        reactions = m.get('reactions')
        if not isinstance(reactions, dict):
            reactions = {}

        formatted_msgs.append({
            'id': m.get('id', ''),
            'sender': m.get('sender', ''),
            'recipient': m.get('recipient', ''),
            'ciphertext': '' if is_deleted else m.get('ciphertext', ''),
            'iv': '' if is_deleted else m.get('iv', ''),
            'timestamp': m.get('timestamp', ''),
            'display_time': m.get('display_time', ''),
            'read': bool(m.get('read', False)),
            'reactions': reactions,
            'deleted': is_deleted,
            'reply_to': m.get('reply_to', None)
        })

    return jsonify({
        'recipient': recipient,
        'messages': formatted_msgs
    })


@app.route('/api/messages/send', methods=['POST'])
@login_required
def api_messages_send():
    cfg = load_config()
    if cfg.get('features', {}).get('messaging') is False:
        return jsonify({'error': 'Messaging is disabled'}), 403

    data = request.get_json(silent=True) or request.form
    recipient = (data.get('recipient') or '').strip()
    ciphertext = (data.get('ciphertext') or '').strip()
    iv = (data.get('iv') or '').strip()
    reply_to = data.get('reply_to')
    if isinstance(reply_to, str) and not reply_to.strip():
        reply_to = None

    if not recipient or not ciphertext or not iv:
        return jsonify({'error': 'Missing recipient or encrypted payload'}), 400

    users = load_users()
    if recipient not in users:
        return jsonify({'error': 'Recipient not found'}), 404

    now = datetime.datetime.now()
    new_msg = {
        'id': secrets.token_hex(8),
        'sender': session['username'],
        'recipient': recipient,
        'ciphertext': ciphertext,
        'iv': iv,
        'timestamp': now.isoformat(),
        'display_time': now.strftime('%I:%M %p').lstrip('0'),
        'read': False,
        'reactions': {},
        'deleted': False,
        'reply_to': reply_to
    }

    with messages_lock:
        messages = load_messages()
        messages.append(new_msg)
        save_messages(messages)

    return jsonify({'success': True, 'message': new_msg})


@app.route('/api/messages/react', methods=['POST'])
@login_required
def api_messages_react():
    cfg = load_config()
    if cfg.get('features', {}).get('messaging') is False:
        return jsonify({'error': 'Messaging is disabled'}), 403

    data = request.get_json(silent=True) or request.form
    message_id = (data.get('message_id') or '').strip()
    reaction = (data.get('reaction') or '').strip()

    if not message_id or not reaction:
        return jsonify({'error': 'Missing message_id or reaction'}), 400

    current_user = session['username']
    role = get_current_role() or session.get('role', 'user')

    with messages_lock:
        messages = load_messages()
        target_msg = next((m for m in messages if m.get('id') == message_id), None)

        if not target_msg:
            return jsonify({'error': 'Message not found'}), 404

        # Ensure message is accessible to current user (must be sender, recipient, or admin)
        if target_msg.get('sender') != current_user and target_msg.get('recipient') != current_user and role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403

        if target_msg.get('deleted'):
            return jsonify({'error': 'Cannot react to a deleted message'}), 400

        # Ensure reactions dictionary exists
        reactions = target_msg.get('reactions')
        if not isinstance(reactions, dict):
            reactions = {}
            target_msg['reactions'] = reactions

        # Toggles reaction: if user already reacted with that emoji, remove it; otherwise add/update it
        if current_user in reactions.get(reaction, []):
            # User already reacted with this emoji -> remove it
            reactions[reaction].remove(current_user)
            if not reactions[reaction]:
                reactions.pop(reaction, None)
        else:
            # Add or update reaction:
            # Tapback convention: remove current_user from any other reaction on this message first
            for emo in list(reactions.keys()):
                if current_user in reactions[emo]:
                    reactions[emo].remove(current_user)
                    if not reactions[emo]:
                        reactions.pop(emo, None)
            # Add current_user to the selected emoji reaction
            if reaction not in reactions:
                reactions[reaction] = []
            reactions[reaction].append(current_user)

        save_messages(messages)
        updated_reactions = target_msg.get('reactions', {})

    return jsonify({
        'success': True,
        'message_id': message_id,
        'reactions': updated_reactions
    })


@app.route('/api/messages/delete/<msg_id>', methods=['POST'])
@login_required
def api_messages_delete(msg_id):
    cfg = load_config()
    if cfg.get('features', {}).get('messaging') is False:
        return jsonify({'error': 'Messaging is disabled'}), 403

    current_user = session['username']
    role = get_current_role() or session.get('role', 'user')

    with messages_lock:
        messages = load_messages()
        target_msg = next((m for m in messages if m.get('id') == msg_id), None)

        if not target_msg:
            return jsonify({'error': 'Message not found'}), 404

        # Checks that the sender is session['username'] or user is admin
        if target_msg.get('sender') != current_user and role != 'admin':
            return jsonify({'error': 'Permission denied: only sender or admin can delete'}), 403

        target_msg['deleted'] = True
        target_msg['ciphertext'] = ""
        target_msg['iv'] = ""
        target_msg['deleted_by'] = current_user
        target_msg['deleted_at'] = datetime.datetime.now().isoformat()

        save_messages(messages)

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'deleted': True
    })


@app.route('/api/messages/clear/<recipient>', methods=['POST'])
@login_required
def api_messages_clear(recipient):
    current_user = session['username']
    with messages_lock:
        messages = load_messages()
        filtered = [
            m for m in messages
            if not ((m.get('sender') == current_user and m.get('recipient') == recipient)
                 or (m.get('sender') == recipient and m.get('recipient') == current_user))
        ]
        save_messages(filtered)
    return jsonify({'success': True})


# Notification Center API

@app.route('/api/notifications')
@login_required
def api_notifications():
    current_user = session['username']
    notifs = []
    latest_unread_id = None

    # 1. Unread Messages Notifications & Audio Chime trigger
    try:
        messages = load_messages()
        unread_by_sender = {}
        unread_messages = []
        for m in messages:
            if m.get('recipient') == current_user and not m.get('read', False) and not m.get('deleted', False):
                sndr = m.get('sender', 'Someone')
                unread_by_sender[sndr] = unread_by_sender.get(sndr, 0) + 1
                unread_messages.append(m)

        if unread_messages:
            unread_messages.sort(key=lambda x: x.get('timestamp', ''))
            latest_unread_id = unread_messages[-1].get('id')

        for sndr, count in unread_by_sender.items():
            notifs.append({
                'id': f'msg_{sndr}',
                'type': 'message',
                'icon': '💬',
                'title': f'New Message ({count})' if count > 1 else 'New Encrypted Message',
                'desc': f'{sndr} sent you {count} new message(s)' if count > 1 else f'{sndr} sent you a message',
                'time': 'Recent',
                'link': 'messages'
            })
    except Exception:
        pass

    # 2. Shared with Me Files
    try:
        shares = load_shares()
        for s in shares:
            if (s.get('shared_with') == current_user or s.get('shared_with') == 'everyone') and s.get('owner') != current_user:
                notifs.append({
                    'id': f"share_{s.get('id')}",
                    'type': 'share',
                    'icon': '📁',
                    'title': 'Shared Item Available',
                    'desc': f"{s.get('owner')} shared '{s.get('name')}' with you",
                    'time': s.get('created_at', 'Recently'),
                    'link': 'files'
                })
    except Exception:
        pass

    # 3. Active Sessions Alert
    try:
        sessions = load_sessions()
        my_sessions = [s for s in sessions if s.get('username') == current_user]
        if len(my_sessions) > 1:
            notifs.append({
                'id': 'sess_multiple',
                'type': 'security',
                'icon': '🔒',
                'title': 'Multiple Active Devices',
                'desc': f'Logged in on {len(my_sessions)} devices. Review in Settings.',
                'time': 'Active now',
                'link': 'account'
            })
    except Exception:
        pass

    # 4. Storage Quota Warning (for non-unlimited users)
    try:
        quota_mb = current_quota_mb()
        if quota_mb:
            home = current_home()
            used_mb = folder_size(home) / (1024 * 1024)
            pct = (used_mb / quota_mb) * 100
            if pct >= 85:
                notifs.append({
                    'id': 'quota_warning',
                    'type': 'storage',
                    'icon': '⚠️',
                    'title': 'Storage Limit Warning',
                    'desc': f'Your quota is {pct:.1f}% full ({human_size(used_mb)} used).',
                    'time': 'Warning',
                    'link': 'account'
                })
    except Exception:
        pass

    return jsonify({
        'count': len(notifs),
        'notifications': notifs,
        'latest_unread_id': latest_unread_id
    })


@app.route('/audio/chime.wav')
def get_chime_audio():
    """Generates a clean Apple-style harmonic chime WAV in-memory."""
    sample_rate = 44100
    duration = 0.35
    num_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            env = math.exp(-7.0 * t)
            # Dual harmonic bell tone (F#5 = 739.99Hz, C#6 = 1108.73Hz)
            sample = env * 0.45 * (math.sin(2 * math.pi * 739.99 * t) + 0.4 * math.sin(2 * math.pi * 1108.73 * t))
            val = int(sample * 32767.0)
            val = max(-32768, min(32767, val))
            frames.extend(val.to_bytes(2, byteorder='little', signed=True))
        wav.writeframes(frames)
    buf.seek(0)
    return Response(buf.read(), mimetype='audio/wav')


# Chat Attachments & NAS File Sharing in Chat

@app.route('/api/messages/upload_attachment', methods=['POST'])
@login_required
def api_messages_upload_attachment():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    if not filename:
        filename = f"file_{secrets.token_hex(4)}"

    # Generate unique filename to avoid collisions
    unique_name = f"{int(datetime.datetime.now().timestamp())}_{secrets.token_hex(4)}_{filename}"
    save_path = os.path.join(CHAT_ATTACHMENTS_DIR, unique_name)
    file.save(save_path)

    ext = os.path.splitext(filename)[1].lower()
    is_img = ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
    size_kb = round(os.path.getsize(save_path) / 1024, 1)

    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('api_messages_get_attachment', filename=unique_name),
        'is_image': is_img,
        'size_kb': size_kb
    })


@app.route('/api/messages/attachment/<filename>')
@login_required
def api_messages_get_attachment(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(CHAT_ATTACHMENTS_DIR, safe_name)


@app.route('/api/messages/my_nas_files')
@login_required
def api_messages_my_nas_files():
    home = current_home()
    items = []
    if os.path.exists(home):
        for root, dirs, files in os.walk(home):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, home).replace('\\', '/')
                ext = os.path.splitext(f)[1].lower()
                is_img = ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
                try:
                    size_kb = round(os.path.getsize(full) / 1024, 1)
                except Exception:
                    size_kb = 0
                items.append({
                    'name': f,
                    'rel_path': rel,
                    'is_image': is_img,
                    'size_kb': size_kb
                })
    return jsonify({'files': items[:50]})


@app.route('/api/messages/attach_nas_file', methods=['POST'])
@login_required
def api_messages_attach_nas_file():
    data = request.get_json(silent=True) or request.form
    rel_path = data.get('rel_path', '').replace('\\', '/').strip('/')
    home = current_home()
    full_path = os.path.normpath(os.path.join(home, rel_path))

    if not full_path.startswith(os.path.abspath(home)) or not os.path.isfile(full_path):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    base_name = secure_filename(os.path.basename(full_path)) or "file"
    unique_name = f"nas_{int(datetime.datetime.now().timestamp())}_{secrets.token_hex(4)}_{base_name}"
    dest_path = os.path.join(CHAT_ATTACHMENTS_DIR, unique_name)

    try:
        shutil.copy2(full_path, dest_path)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    ext = os.path.splitext(base_name)[1].lower()
    is_img = ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
    size_kb = round(os.path.getsize(dest_path) / 1024, 1)

    return jsonify({
        'success': True,
        'filename': base_name,
        'url': url_for('api_messages_get_attachment', filename=unique_name),
        'is_image': is_img,
        'size_kb': size_kb
    })


@app.route('/shared/raw/<share_id>')
@login_required
def shared_raw(share_id):
    shares = load_shares()
    share = next((s for s in shares if s.get('id') == share_id), None)
    if not share:
        abort(404)

    current_user = session['username']
    live_role = get_current_role() or session.get('role', 'user')
    if not (share['shared_with'] in (current_user, 'everyone') or
            share['owner'] == current_user or live_role == 'admin'):
        abort(403)

    abs_path = share['abs_path']
    if not os.path.isfile(abs_path):
        abort(404)

    import mimetypes
    mtype, _ = mimetypes.guess_type(abs_path)
    ext = os.path.splitext(abs_path)[1].lower()
    text_code_exts = {
        '.py': 'text/plain; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8',
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8',
        '.md': 'text/plain; charset=utf-8',
        '.sh': 'text/plain; charset=utf-8',
        '.csv': 'text/plain; charset=utf-8',
        '.svg': 'image/svg+xml',
    }
    if ext in text_code_exts:
        mtype = text_code_exts[ext]
    elif not mtype:
        mtype = 'application/octet-stream'

    return send_from_directory(
        os.path.dirname(abs_path),
        os.path.basename(abs_path),
        as_attachment=False,
        mimetype=mtype
    )


UPDATE_STATE = {
    'status': 'idle',  # 'idle' | 'checking' | 'downloading' | 'staged' | 'countdown' | 'restarting' | 'error'
    'countdown': 0,
    'has_update': False,
    'current_version': '1.0',
    'latest_version': '1.0.0',
    'latest_commit_sha': None,
    'last_checked': None,
    'release_notes': '',
    'repo_url': 'https://github.com/fanumtalkstech/Karis-NAS',
    'download_url': 'https://github.com/fanumtalkstech/Karis-NAS/archive/refs/heads/main.zip',
    'staged_dir': os.path.join(BASE_DIR, '.update_staged'),
    'zip_file': os.path.join(BASE_DIR, '.update_download.zip'),
    'error_message': None,
    'download_progress': 0
}
UPDATE_LOCK = threading.Lock()

STAGE_DEV = 0
STAGE_ALPHA = 1
STAGE_BETA = 2
STAGE_RC = 3
STAGE_FINAL = 4

STAGE_NAMES = {
    STAGE_DEV: 'dev',
    STAGE_ALPHA: 'alpha',
    STAGE_BETA: 'beta',
    STAGE_RC: 'rc',
    STAGE_FINAL: 'final'
}

def parse_version(v_str):
    """Parse version string into normalized tuple (major, minor, patch, subpatch, stage, iteration)."""
    if not v_str:
        return (0, 0, 0, 0, STAGE_FINAL, 0)

    s = str(v_str).strip()

    # Strip leading 'v' or 'V' if followed by a digit or separator
    if s.lower().startswith('v') and len(s) > 1 and (s[1].isdigit() or s[1] in '.-_'):
        s = s[1:].strip()

    stage = STAGE_FINAL
    stage_iter = 0

    # Match pre-release identifiers with word or punctuation boundaries
    # Supports: 'beta 3', 'beta-3', 'beta.3', 'b3', 'rc1', 'preview2', 'alpha', 'dev'
    pattern = r'(?i)(?:^|[-_.\s])(dev|alpha|preview|rc|beta|b|a)(?:[-_.\s]*(\d+))?'
    match = re.search(pattern, s)

    # Secondary check for compact notation e.g. '1.0b4' or '1.0rc1'
    if not match:
        match = re.search(r'(?i)(?<=\d)(b|a|rc|dev)(\d+)?', s)

    if match:
        st_name = match.group(1).lower()
        st_num = match.group(2)
        
        # Iteration defaults to 1 if stage keyword is present without a number (e.g. '1.0-beta')
        if st_num and st_num.isdigit():
            stage_iter = int(st_num)
        elif st_name in ('beta', 'b', 'alpha', 'a', 'rc', 'preview'):
            stage_iter = 1
        else:
            stage_iter = 0

        if st_name in ('dev',):
            stage = STAGE_DEV
        elif st_name in ('alpha', 'a'):
            stage = STAGE_ALPHA
        elif st_name in ('beta', 'b'):
            stage = STAGE_BETA
        elif st_name in ('rc', 'preview'):
            stage = STAGE_RC

        # Remove the stage substring to cleanly isolate numeric release numbers
        base_part = s[:match.start()] + ' ' + s[match.end():]
    else:
        base_part = s

    # Extract all digits sequences for base numbers
    num_strs = re.findall(r'\d+', base_part)
    nums = [int(n) for n in num_strs]

    major = nums[0] if len(nums) > 0 else 0
    minor = nums[1] if len(nums) > 1 else 0
    patch = nums[2] if len(nums) > 2 else 0
    subpatch = nums[3] if len(nums) > 3 else 0

    return (major, minor, patch, subpatch, stage, stage_iter)


def is_newer_version(remote, local):
    """Check if remote version is strictly newer than local version."""
    return parse_version(remote) > parse_version(local)


def perform_github_check():
    """
    Poll GitHub API for the latest release/tag/commit in fanumtalkstech/Karis-NAS.
    Compares the remote version tag against local current_version using SemVer precedence.
    """
    with UPDATE_LOCK:
        cfg = load_config()
        repo = cfg.get('github_repo', 'fanumtalkstech/Karis-NAS')
        curr_ver = cfg.get('current_version', '1.0')
        
        UPDATE_STATE['status'] = 'checking'
        UPDATE_STATE['repo_url'] = f"https://github.com/{repo}"
        UPDATE_STATE['current_version'] = curr_ver
        UPDATE_STATE['error_message'] = None
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        UPDATE_STATE['last_checked'] = now_str

    headers = {
        'User-Agent': 'Karis-NAS-Updater/1.0',
        'Accept': 'application/vnd.github.v3+json'
    }

    remote_version = None
    release_notes = ''
    download_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
    commit_sha = None

    # Tier 1: Query GitHub Releases (/releases includes pre-releases & regular releases)
    try:
        releases_url = f"https://api.github.com/repos/{repo}/releases"
        req = urllib.request.Request(releases_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            releases = json.loads(resp.read().decode('utf-8'))
            if isinstance(releases, list) and len(releases) > 0:
                latest_rel = releases[0]
                remote_version = latest_rel.get('tag_name') or latest_rel.get('name')
                release_notes = latest_rel.get('body') or latest_rel.get('name', '')
                download_url = latest_rel.get('zipball_url') or f"https://github.com/{repo}/archive/refs/tags/{remote_version}.zip"
    except Exception:
        pass

    # Tier 2: If no releases found, query Git Tags (/tags)
    if not remote_version:
        try:
            tags_url = f"https://api.github.com/repos/{repo}/tags"
            req = urllib.request.Request(tags_url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                tags = json.loads(resp.read().decode('utf-8'))
                if isinstance(tags, list) and len(tags) > 0:
                    latest_tag = tags[0]
                    remote_version = latest_tag.get('name')
                    commit_sha = latest_tag.get('commit', {}).get('sha')
                    download_url = latest_tag.get('zipball_url') or f"https://github.com/{repo}/archive/refs/tags/{remote_version}.zip"
                    release_notes = f"Release tag {remote_version} on GitHub"
        except Exception:
            pass

    # Tier 3: Fallback to main branch commit
    if not remote_version:
        try:
            commits_url = f"https://api.github.com/repos/{repo}/commits/main"
            req = urllib.request.Request(commits_url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                cdata = json.loads(resp.read().decode('utf-8'))
                commit_sha = cdata.get('sha', '')
                c_msg = cdata.get('commit', {}).get('message', '').strip()
                # Check if commit message declares a version like 'Release 1.0 Beta 4' or 'v1.2.1'
                v_match = re.search(r'(?i)v?(\d+\.\d+(?:[.-][a-zA-Z0-9.]+)?)', c_msg)
                if v_match:
                    remote_version = v_match.group(1)
                else:
                    remote_version = curr_ver
                release_notes = c_msg
                download_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
        except Exception as e:
            with UPDATE_LOCK:
                UPDATE_STATE['error_message'] = f"Unable to connect to GitHub: {str(e)}"
                UPDATE_STATE['status'] = 'idle'
                return UPDATE_STATE

    # Determine if remote version is strictly newer
    effective_remote = remote_version or curr_ver
    has_update = is_newer_version(effective_remote, curr_ver)

    with UPDATE_LOCK:
        UPDATE_STATE['latest_version'] = effective_remote
        UPDATE_STATE['latest_commit_sha'] = commit_sha
        UPDATE_STATE['download_url'] = download_url
        UPDATE_STATE['release_notes'] = release_notes
        UPDATE_STATE['has_update'] = has_update
        if has_update:
            UPDATE_STATE['message'] = f"Update available: {effective_remote} (Current: {curr_ver})"
        else:
            UPDATE_STATE['message'] = f"Karis-NAS is up to date (Version {curr_ver})"
        UPDATE_STATE['status'] = 'idle'
        return UPDATE_STATE


def github_hourly_worker():
    """Background thread that executes hourly update check."""
    # Short initial sleep so server startup finishes cleanly
    time.sleep(15)
    while True:
        try:
            cfg = load_config()
            if cfg.get('check_github_updates_hourly', True) or cfg.get('auto_update_hourly', True):
                perform_github_check()
        except Exception:
            pass

        # Sleep for 1 hour (3600 seconds) in 10s increments for graceful responsiveness
        for _ in range(360):
            time.sleep(10)


# Start background worker daemon thread
_updater_thread = threading.Thread(target=github_hourly_worker, daemon=True, name="GitHubHourlyUpdater")
_updater_thread.start()


# System update and restart

@app.route('/api/system/check_update', methods=['GET', 'POST'])
@login_required
def api_system_check_update():
    """Check GitHub repository for new commits/releases."""
    res = perform_github_check()
    with UPDATE_LOCK:
        return jsonify({
            'success': True,
            'has_update': bool(UPDATE_STATE.get('has_update', False)),
            'current_version': UPDATE_STATE.get('current_version', '1.0'),
            'latest_version': UPDATE_STATE.get('latest_version', '1.0.0'),
            'latest_commit_sha': UPDATE_STATE.get('latest_commit_sha'),
            'repo_url': UPDATE_STATE.get('repo_url'),
            'release_notes': UPDATE_STATE.get('release_notes', ''),
            'last_checked': UPDATE_STATE.get('last_checked'),
            'error': UPDATE_STATE.get('error_message')
        })


@app.route('/api/system/update_status', methods=['GET'])
@login_required
def api_system_update_status():
    """Query current update engine status, countdown, and download state."""
    with UPDATE_LOCK:
        return jsonify({
            'status': UPDATE_STATE.get('status', 'idle'),
            'countdown': UPDATE_STATE.get('countdown', 0),
            'has_update': bool(UPDATE_STATE.get('has_update', False)),
            'current_version': UPDATE_STATE.get('current_version', '1.0'),
            'latest_version': UPDATE_STATE.get('latest_version', '1.0.0'),
            'repo_url': UPDATE_STATE.get('repo_url'),
            'release_notes': UPDATE_STATE.get('release_notes', ''),
            'last_checked': UPDATE_STATE.get('last_checked'),
            'error': UPDATE_STATE.get('error_message')
        })


@app.route('/api/system/download_update', methods=['POST'])
@app.route('/api/system/update', methods=['POST'])
@login_required
def api_system_download_update():
    """Download latest release archive from GitHub, verify zip, stage payload, and create automatic backup."""
    if get_current_role() != 'admin':
        abort(403)

    with UPDATE_LOCK:
        if UPDATE_STATE['status'] in ('downloading', 'restarting'):
            return jsonify({'success': False, 'error': f"Operation in progress: {UPDATE_STATE['status']}"}), 400
        UPDATE_STATE['status'] = 'downloading'
        UPDATE_STATE['error_message'] = None

    try:
        cfg = load_config()
        repo = cfg.get('github_repo', 'fanumtalkstech/Karis-NAS')
        zip_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
        zip_dest = os.path.join(BASE_DIR, '.update_download.zip')
        staged_dir = os.path.join(BASE_DIR, '.update_staged')

        # 1. Download zip archive from GitHub
        req = urllib.request.Request(
            zip_url,
            headers={'User-Agent': 'Karis-NAS-Updater/1.0'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_dest, 'wb') as out_f:
            shutil.copyfileobj(resp, out_f)

        # 2. Verify zip archive integrity
        if not zipfile.is_zipfile(zip_dest):
            raise ValueError("Downloaded file is not a valid zip archive.")

        with zipfile.ZipFile(zip_dest, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file:
                raise ValueError(f"Corrupt file in archive: {bad_file}")

            # 3. Clean and unpack to staged folder
            if os.path.exists(staged_dir):
                shutil.rmtree(staged_dir, ignore_errors=True)
            os.makedirs(staged_dir, exist_ok=True)
            zf.extractall(staged_dir)

        # 4. Locate repo root folder inside extracted archive (e.g. Karis-NAS-main/)
        subdirs = [os.path.join(staged_dir, d) for d in os.listdir(staged_dir) if os.path.isdir(os.path.join(staged_dir, d))]
        payload_root = subdirs[0] if subdirs else staged_dir

        # Validate that essential files are present in the update payload
        has_app = os.path.exists(os.path.join(payload_root, 'app.py'))
        has_templates = os.path.exists(os.path.join(payload_root, 'templates'))
        if not has_app and not has_templates:
            raise ValueError("Update payload missing essential files (app.py or templates).")

        # 5. Create automatic safety backup of current installation before staging
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(BASE_DIR, 'backups', f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)
        
        current_app = os.path.join(BASE_DIR, 'app.py')
        current_templates = os.path.join(BASE_DIR, 'templates')
        if os.path.exists(current_app):
            shutil.copy2(current_app, os.path.join(backup_dir, 'app.py'))
        if os.path.exists(current_templates):
            shutil.copytree(current_templates, os.path.join(backup_dir, 'templates'), dirs_exist_ok=True)

        with UPDATE_LOCK:
            UPDATE_STATE['status'] = 'staged'
            UPDATE_STATE['staged_dir'] = payload_root

        return jsonify({
            'success': True,
            'status': 'staged',
            'message': f"Update downloaded and verified. Safety backup created in backups/backup_{timestamp}.",
            'backup_folder': f"backups/backup_{timestamp}"
        })

    except Exception as e:
        with UPDATE_LOCK:
            UPDATE_STATE['status'] = 'error'
            UPDATE_STATE['error_message'] = str(e)
        return jsonify({'success': False, 'error': str(e)}), 500


def _apply_and_restart_worker():
    """Worker that handles 60-second warning countdown and triggers update replacement + self-restart."""
    staged_root = UPDATE_STATE.get('staged_dir')
    if not staged_root or not os.path.exists(staged_root):
        staged_root = os.path.join(BASE_DIR, '.update_staged')
        subdirs = [os.path.join(staged_root, d) for d in os.listdir(staged_root) if os.path.isdir(os.path.join(staged_root, d))]
        if subdirs:
            staged_root = subdirs[0]

    # Countdown loop
    for remaining in range(60, 0, -1):
        with UPDATE_LOCK:
            if UPDATE_STATE['status'] != 'countdown':
                return  # Cancelled
            UPDATE_STATE['countdown'] = remaining
        time.sleep(1)

    # Apply update files
    with UPDATE_LOCK:
        UPDATE_STATE['status'] = 'restarting'
        UPDATE_STATE['countdown'] = 0

    try:
        # Copy app.py
        new_app = os.path.join(staged_root, 'app.py')
        if os.path.exists(new_app):
            shutil.copy2(new_app, os.path.join(BASE_DIR, 'app.py'))

        # Copy requirements.txt if present
        new_req = os.path.join(staged_root, 'requirements.txt')
        if os.path.exists(new_req):
            shutil.copy2(new_req, os.path.join(BASE_DIR, 'requirements.txt'))

        # Copy templates
        new_templates = os.path.join(staged_root, 'templates')
        dest_templates = os.path.join(BASE_DIR, 'templates')
        if os.path.exists(new_templates):
            os.makedirs(dest_templates, exist_ok=True)
            for t_item in os.listdir(new_templates):
                s_t = os.path.join(new_templates, t_item)
                d_t = os.path.join(dest_templates, t_item)
                if os.path.isfile(s_t):
                    shutil.copy2(s_t, d_t)

        # Update config with new commit sha / version
        cfg = load_config()
        if UPDATE_STATE.get('latest_commit_sha'):
            cfg['last_commit_sha'] = UPDATE_STATE['latest_commit_sha']
        if UPDATE_STATE.get('latest_version'):
            cfg['current_version'] = UPDATE_STATE['latest_version']
        save_config(cfg)

        # Clean up staging zip and directory
        zip_dest = os.path.join(BASE_DIR, '.update_download.zip')
        if os.path.exists(zip_dest):
            os.remove(zip_dest)
        staged_container = os.path.join(BASE_DIR, '.update_staged')
        if os.path.exists(staged_container):
            shutil.rmtree(staged_container, ignore_errors=True)

    except Exception as e:
        with UPDATE_LOCK:
            UPDATE_STATE['status'] = 'error'
            UPDATE_STATE['error_message'] = f"Failed to replace files: {e}"
        return

    # Trigger process restart
    _spawn_detached_server()


def _spawn_detached_server():
    """Spawn detached Python process and terminate current process."""
    try:
        if os.name == 'nt':
            # Windows detached process flags
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=BASE_DIR,
                close_fds=True,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix detached process
            subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=BASE_DIR,
                close_fds=True,
                start_new_session=True
            )
    except Exception as e:
        pass

    # Give current request 1.5 seconds to return HTTP response, then terminate cleanly
    threading.Timer(1.5, lambda: os._exit(0)).start()


@app.route('/api/system/apply_update', methods=['POST'])
@login_required
def api_system_apply_update():
    """Initiate a 60-second warning countdown and automated update replacement."""
    if get_current_role() != 'admin':
        abort(403)

    data = request.get_json(silent=True) or {}
    immediate = bool(data.get('immediate', False))

    with UPDATE_LOCK:
        if UPDATE_STATE['status'] == 'downloading':
            return jsonify({'success': False, 'error': 'Update is currently downloading.'}), 400

        # If immediate is requested or if already countdown
        if immediate:
            UPDATE_STATE['status'] = 'restarting'
            UPDATE_STATE['countdown'] = 0
            # Execute in thread to return response
            t = threading.Thread(target=lambda: (_apply_and_restart_worker()), daemon=True)
            t.start()
            return jsonify({
                'success': True,
                'status': 'restarting',
                'message': 'Applying update immediately and restarting server...'
            })

        UPDATE_STATE['status'] = 'countdown'
        UPDATE_STATE['countdown'] = 60

    t = threading.Thread(target=_apply_and_restart_worker, daemon=True, name="UpdateCountdownWorker")
    t.start()

    return jsonify({
        'success': True,
        'status': 'countdown',
        'countdown': 60,
        'message': 'Update staged. Server will apply files and restart in 60 seconds.'
    })


@app.route('/api/system/restart', methods=['POST'])
@login_required
def api_system_restart():
    """Spawn detached Python process and terminate old process so server restarts automatically."""
    if get_current_role() != 'admin':
        abort(403)

    with UPDATE_LOCK:
        UPDATE_STATE['status'] = 'restarting'

    _spawn_detached_server()

    return jsonify({
        'success': True,
        'status': 'restarting',
        'message': 'Server restart signal sent. Reconnecting in a few moments...'
    })


if __name__ == '__main__':
    ssl_context = None
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        ssl_context = (CERT_FILE, KEY_FILE)
        print(" * [HTTPS Mode Active] Using SSL Certificate: cert.pem & key.pem")
        print(" * Access Portal securely at: https://192.168.1.252:3251 or https://localhost:3251")
    else:
        print(" * [HTTP Mode] To enable permanent HTTPS, place cert.pem and key.pem in {BASE_DIR}")
        print(" * Access Portal at: http://192.168.1.252:3251 or http://localhost:3251")
    app.run(host='0.0.0.0', port=3251, debug=False, ssl_context=ssl_context)


@app.route('/api/system/ping')
def api_system_ping():
    return jsonify({
        'status': 'ok',
        'online': True,
        'app': 'Karis-NAS',
        'version': load_config().get('current_version', '1.0')
    })


@app.route('/api/system/update_hourly_pref', methods=['POST'])
@login_required
def api_system_update_hourly_pref():
    cfg = load_config()
    data = request.get_json(silent=True) or request.form
    enabled = data.get('enabled')
    if isinstance(enabled, str):
        enabled = enabled.lower() in ('true', '1', 'yes', 'on')
    else:
        enabled = bool(enabled)
    cfg['check_github_updates_hourly'] = enabled
    save_config(cfg)
    return jsonify({'success': True, 'check_github_updates_hourly': enabled})
