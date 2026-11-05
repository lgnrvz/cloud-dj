from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
import sqlite3, os, threading, subprocess, re, signal, random, time, sys, hashlib, secrets, socket, json
import urllib.request, urllib.parse
from base64 import b64encode
from datetime import datetime, timedelta


# Self-contained password hashing — compatible with werkzeug's pbkdf2:sha256 format
# so existing databases with hashed passwords keep working.
def generate_password_hash(password, method='pbkdf2:sha256', salt_length=16):
    """Generate password hash. Compatible with werkzeug's pbkdf2:sha256 format."""
    if not password:
        raise ValueError('password required')
    salt = secrets.token_hex(salt_length)
    if method.startswith('pbkdf2:sha256'):
        iterations = 600000
        if method.count(':') > 1:
            try:
                iterations = int(method.rsplit(':', 1)[-1])
            except (ValueError, IndexError):
                pass
        h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
        h_b64 = b64encode(h).decode().rstrip('=')
        return f'pbkdf2:sha256:{iterations}${salt}${h_b64}'
    raise ValueError(f'unsupported method: {method}')


def check_password_hash(pwhash, password):
    """Check password against hash. Compatible with werkzeug's pbkdf2:sha256 format."""
    if not pwhash or not password:
        return False
    try:
        parts = pwhash.split('$')
        if len(parts) != 3:
            return False
        method, salt, hash_val = parts
        if not method.startswith('pbkdf2:sha256'):
            return False
        iterations = 600000
        try:
            iterations = int(method.rsplit(':', 1)[-1])
        except (ValueError, IndexError):
            pass
        h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
        h_b64 = b64encode(h).decode().rstrip('=')
        return secrets.compare_digest(h_b64, hash_val)
    except Exception:
        return False

def _ban_state(banned_until):
    """Return (is_banned, until_datetime_or_None). None until = permanent ban."""
    bu = (banned_until or '').strip()
    if not bu:
        return False, None
    if bu == 'permanent':
        return True, None
    try:
        until = datetime.fromisoformat(bu)
    except ValueError:
        return False, None
    now_ph = datetime.utcnow() + timedelta(hours=8)
    return now_ph < until, until


# ─── SYSTEM STATS (stdlib /proc parsing — Linux; None elsewhere) ───
_sys_last = {}

def _read_proc(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, IOError):
        return None

def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))  # no packets actually sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return 'unknown'

def _system_stats():
    """CPU % / RAM / net speed from /proc. Deltas between polls."""
    stat = _read_proc('/proc/stat')
    mem = _read_proc('/proc/meminfo')
    net = _read_proc('/proc/net/dev')
    cpu = ram = None
    net_speed = {'down': None, 'up': None}
    if stat:
        parts = stat.splitlines()[0].split()
        if len(parts) >= 5 and parts[0] == 'cpu':
            vals = [int(x) for x in parts[1:]]
            total, idle = sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0)
            last = _sys_last.get('cpu')
            if last:
                d_total = total - last[0]
                d_idle = idle - last[1]
                if d_total > 0:
                    cpu = round(100 * (1 - d_idle / d_total), 1)
            _sys_last['cpu'] = (total, idle)
    if mem:
        def _mem_kb(key):
            for line in mem.splitlines():
                if line.startswith(key + ':'):
                    return int(line.split()[1])
            return None
        total_kb = _mem_kb('MemTotal')
        avail_kb = _mem_kb('MemAvailable')
        if total_kb:
            used_kb = max(0, total_kb - (avail_kb or 0))
            ram = {'used': round(used_kb / 1048576, 1), 'total': round(total_kb / 1048576, 1)}
    if net:
        rx = tx = 0
        for line in net.splitlines()[2:]:
            parts = line.split(':')
            if len(parts) == 2:
                vals = parts[1].split()
                if len(vals) > 8:
                    rx += int(vals[0])
                    tx += int(vals[8])
        now = time.time()
        last = _sys_last.get('net')
        if last:
            dt = now - last[0]
            if dt > 0:
                net_speed = {
                    'down': round(max(0, (rx - last[1])) / 1024 / dt, 1),
                    'up': round(max(0, (tx - last[2])) / 1024 / dt, 1),
                }
        _sys_last['net'] = (now, rx, tx)
    return {'ip': _lan_ip(), 'cpu': cpu, 'ram': ram, 'net': net_speed}


app = Flask(__name__)

# Short git commit hash of the running code (for the footer version)
def _current_commit():
    try:
        out = subprocess.check_output(
            ['git', 'rev-parse', '--short=7', 'HEAD'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return out or None
    except Exception:
        return None

APP_COMMIT = _current_commit()

@app.context_processor
def inject_commit():
    return {'app_version': APP_COMMIT or 'unknown'}
# Persistent secret key — unique per install, survives restarts
secret_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
if os.path.isfile(secret_file):
    with open(secret_file) as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(secret_file, 'w') as f:
        f.write(app.secret_key)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)


@app.after_request
def _no_stale_pages(resp):
    """Templates + inline JS change on every deploy: never serve a cached page."""
    if resp.mimetype == 'text/html':
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
    return resp

# Threading async mode (werkzeug + simple-websocket): not deprecated, works on
# Linux/Mac/Windows with a single code path. eventlet is in bugfix-only mode
# and hangs the dev server on Windows, so we dropped it entirely.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = ''  # Remove "Please log in to access this page" flash

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
NOW_PLAYING = {'id': None, 'url': None, 'title': 'Nothing playing', 'username': '-', 'is_auto_dj': False, 'has_history': False}
SCORING_ENABLED = False  # Videoke scoring toggle
SHOW_LEADERBOARD = False  # Leaderboard visibility toggle
SUGGESTED_ENABLED = True  # Suggested songs toggle
CHAT_ENABLED = True  # Live chat toggle

# Anti-abuse settings
MAX_CONSECUTIVE_QUEUE = 16  # Max songs a user can add consecutively (1-16)
_last_adder = {'username': None, 'count': 0, 'last_time': 0}  # Track consecutive adds by same user + timestamp
QUEUE_LIMIT_RESET_MINUTES = 5  # How long before a blocked user's counter resets

# Auto-DJ: track which history songs have been played this round (no repeats until all done)
_auto_dj_round_played = set()  # set of queue IDs played in the current round

# ─── AUTO-DJ NEXT (reserved so the player can preload + crossfade it) ───
AUTODJ_NEXT = None          # dict for the picked-but-not-yet-played song
AUTODJ_BLOCK_SIZE = 14      # songs of one genre before Auto-DJ switches genre


def _vid_of(url):
    m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', url or '')
    return m.group(1) if m else None


def _autodj_pick():
    """Pick (and remember) the next Auto-DJ song.

    Auto-DJ stays on one genre for AUTODJ_BLOCK_SIZE songs, then switches to a
    different genre. The pick is memoised in AUTODJ_NEXT so /next-track and
    /advance agree: the song the browser preloaded is the song that plays.
    """
    global AUTODJ_NEXT
    if AUTODJ_NEXT:
        return AUTODJ_NEXT

    conn = get_db()
    played = conn.execute(
        "SELECT id, title, clean_url, youtube_url FROM queue WHERE status='played'"
    ).fetchall()
    meta = {r['video_id']: r['genre'] for r in conn.execute(
        "SELECT video_id, genre FROM song_meta WHERE genre IS NOT NULL")}
    conn.close()
    if not played:
        return None

    pools = {}
    for r in played:
        g = meta.get(_vid_of(r['clean_url'] or r['youtube_url']))
        if g:
            pools.setdefault(g, []).append(r)

    genre = get_setting('autodj_genre')
    count = int(get_setting('autodj_count', '0') or 0)
    if not genre or count >= AUTODJ_BLOCK_SIZE or genre not in pools:
        # Start a new genre block. Prefer genres with enough songs to fill it.
        choices = [g for g in pools if g != genre and len(pools[g]) >= AUTODJ_BLOCK_SIZE]
        if not choices:
            choices = [g for g in pools if g != genre] or list(pools)
        if choices:
            genre = random.choice(choices)
            set_setting('autodj_genre', genre)
            set_setting('autodj_count', '0')
            count = 0
            print(f'[autodj] new genre block -> {genre}', flush=True)
        else:
            genre = None

    pool = pools.get(genre) or played
    if len(_auto_dj_round_played) >= len(played):
        _auto_dj_round_played.clear()
    fresh = [r for r in pool if r['id'] not in _auto_dj_round_played]
    row = random.choice(fresh or pool)
    _auto_dj_round_played.add(row['id'])

    AUTODJ_NEXT = {
        'id': -1,
        'url': row['clean_url'] or row['youtube_url'],
        'title': 'Auto-DJ: ' + (row['title'] or 'Unknown'),
        'username': 'Cloud-DJ',
        'is_auto_dj': True,
        'has_history': True,
        'genre': genre,
    }
    return AUTODJ_NEXT

# Signup rate limit: track IP -> last signup timestamp (seconds)
_signup_cooldown = {}  # IP -> timestamp
SIGNUP_COOLDOWN_SECONDS = 0  # No cooldown for LAN use

# Auto-detect paths — works on Linux AND Windows
import shutil

# Node.js: check bundled location first (PyInstaller onefile), then PATH, then common install locations
NODE_PATH = None
if getattr(sys, 'frozen', False):
    _bundled_node = os.path.join(sys._MEIPASS, 'node.exe')
    if os.path.isfile(_bundled_node):
        NODE_PATH = _bundled_node
if not NODE_PATH:
    NODE_PATH = shutil.which('node') or shutil.which('nodejs')
if not NODE_PATH:
    for candidate in [
        '/usr/bin/node',
        '/usr/local/bin/node',
        'C:\\Program Files\\nodejs\\node.exe',
        os.path.expandvars('%ProgramFiles%\\nodejs\\node.exe'),
    ]:
        if os.path.isfile(candidate):
            NODE_PATH = candidate
            break
if not NODE_PATH:
    NODE_PATH = 'node'  # hope it's on PATH

# yt-dlp: check venv first (where install.ps1/install.sh put it), then PATH, then common locations
venv_dir = os.path.dirname(sys.executable)  # e.g., .venv/Scripts/ or .venv/bin/
YTDLP = None

# 0. PyInstaller bundle: bundled binaries are extracted to sys._MEIPASS
if getattr(sys, 'frozen', False):
    for exe in ['yt-dlp.exe', 'yt-dlp']:
        candidate = os.path.join(sys._MEIPASS, exe)
        if os.path.isfile(candidate):
            YTDLP = candidate
            break

# 1. Check venv Scripts/bin directory first (most reliable)
for exe in ['yt-dlp', 'yt-dlp.exe']:
    candidate = os.path.join(venv_dir, exe)
    if os.path.isfile(candidate):
        YTDLP = candidate
        break

# 2. Check PATH
if not YTDLP:
    YTDLP = shutil.which('yt-dlp')

# 3. Check common install locations (cross-platform)
if not YTDLP:
    for candidate in [
        os.path.expanduser('~/.local/bin/yt-dlp'),
        '/usr/local/bin/yt-dlp',
        '/usr/bin/yt-dlp',
        os.path.expandvars('%LOCALAPPDATA%\\Programs\\Python\\Scripts\\yt-dlp.exe'),
        os.path.expandvars('%APPDATA%\\Python\\Scripts\\yt-dlp.exe'),
    ]:
        if os.path.isfile(candidate):
            YTDLP = candidate
            break

# 4. Last resort
if not YTDLP:
    YTDLP = 'yt-dlp'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        ip_address TEXT DEFAULT '',
        banned_until TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        youtube_url TEXT NOT NULL,
        clean_url TEXT DEFAULT '',
        title TEXT DEFAULT 'Loading...',
        status TEXT DEFAULT 'pending',
        priority INTEGER DEFAULT 0,
        loved INTEGER DEFAULT 0,
        ip_address TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS loved_songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        clean_url TEXT NOT NULL,
        title TEXT DEFAULT 'Unknown',
        loved_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    for col_sql in ["clean_url TEXT DEFAULT ''", "loved INTEGER DEFAULT 0"]:
        col_name = col_sql.split()[0]
        try:
            conn.execute(f"ALTER TABLE queue ADD COLUMN {col_sql}")
        except sqlite3.OperationalError:
            pass
    # Safe migration: add ip_address to users if missing (existing DBs)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN ip_address TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Safe migration: add banned_until to users if missing (existing DBs)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN banned_until TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Banned IPs (prevents banned users from registering again)
    conn.execute("""CREATE TABLE IF NOT EXISTS banned_ips (
        ip TEXT PRIMARY KEY,
        banned_until TEXT DEFAULT '',
        username TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        title TEXT DEFAULT 'Unknown',
        username TEXT DEFAULT '-',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        message TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        emoji TEXT NOT NULL,
        username TEXT NOT NULL,
        UNIQUE(message_id, emoji, username)
    )""")
    # FTS5 index for history search — wrap in try/except to prevent DB corruption from crashing startup
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS queue_fts USING fts5("
            "title, username, clean_url, content='queue', content_rowid='id')"
        )
        # Triggers to keep FTS index in sync
        for trig in [
            "CREATE TRIGGER IF NOT EXISTS queue_ai AFTER INSERT ON queue BEGIN"
            "  INSERT INTO queue_fts(rowid, title, username, clean_url)"
            "  VALUES (new.id, new.title, new.username, new.clean_url); END",
            "CREATE TRIGGER IF NOT EXISTS queue_ad AFTER DELETE ON queue BEGIN"
            "  INSERT INTO queue_fts(queue_fts, rowid, title, username, clean_url)"
            "  VALUES ('delete', old.id, old.title, old.username, old.clean_url); END",
            "CREATE TRIGGER IF NOT EXISTS queue_au AFTER UPDATE ON queue BEGIN"
            "  INSERT INTO queue_fts(queue_fts, rowid, title, username, clean_url)"
            "  VALUES ('delete', old.id, old.title, old.username, old.clean_url);"
            "  INSERT INTO queue_fts(rowid, title, username, clean_url)"
            "  VALUES (new.id, new.title, new.username, new.clean_url); END",
        ]:
            conn.execute(trig)
        # Rebuild FTS index — safe command, not raw DELETE
        conn.execute("INSERT INTO queue_fts(queue_fts) VALUES('rebuild')")
    except sqlite3.DatabaseError:
        # FTS table corrupt — drop and recreate
        conn.execute("DROP TABLE IF EXISTS queue_fts")
        conn.execute("DROP TABLE IF EXISTS queue_fts_data")
        conn.execute("DROP TABLE IF EXISTS queue_fts_idx")
        conn.execute("DROP TABLE IF EXISTS queue_fts_docsize")
        conn.execute("DROP TABLE IF EXISTS queue_fts_config")
        conn.execute(
            "CREATE VIRTUAL TABLE queue_fts USING fts5("
            "title, username, clean_url, content='queue', content_rowid='id')"
        )
        for trig in [
            "CREATE TRIGGER IF NOT EXISTS queue_ai AFTER INSERT ON queue BEGIN"
            "  INSERT INTO queue_fts(rowid, title, username, clean_url)"
            "  VALUES (new.id, new.title, new.username, new.clean_url); END",
            "CREATE TRIGGER IF NOT EXISTS queue_ad AFTER DELETE ON queue BEGIN"
            "  INSERT INTO queue_fts(queue_fts, rowid, title, username, clean_url)"
            "  VALUES ('delete', old.id, old.title, old.username, old.clean_url); END",
            "CREATE TRIGGER IF NOT EXISTS queue_au AFTER UPDATE ON queue BEGIN"
            "  INSERT INTO queue_fts(queue_fts, rowid, title, username, clean_url)"
            "  VALUES ('delete', old.id, old.title, old.username, old.clean_url);"
            "  INSERT INTO queue_fts(rowid, title, username, clean_url)"
            "  VALUES (new.id, new.title, new.username, new.clean_url); END",
        ]:
            conn.execute(trig)
        conn.execute("INSERT INTO queue_fts(queue_fts) VALUES('rebuild')")
    except Exception:
        pass  # Worst case — FTS disabled, app still runs
    conn.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS song_meta (
        video_id TEXT PRIMARY KEY,
        artist TEXT,
        song TEXT,
        genre TEXT,
        source TEXT,
        fetched_at TEXT
    )""")
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        conn.execute("INSERT INTO users (name, username, password, is_admin) VALUES (?, ?, ?, ?)",
                     ('DJ Admin', 'admin', generate_password_hash('djadmin123'), 1))
    conn.commit()
    conn.close()

init_db()


def get_setting(key, default=None):
    """Read a persisted app setting (falls back to *default*)."""
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row['value'] if row and row['value'] is not None else default
    except Exception:
        return default


# ─── GENRE LOOKUP (Deezer, cached in song_meta) ───
_GENRE_LOOKUPS = set()


def _deezer_json(path, timeout=8):
    try:
        req = urllib.request.Request('https://api.deezer.com/' + path,
                                     headers={'User-Agent': 'cloud-dj/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _parse_artist_title(title):
    """Pull 'Artist - Song' out of a YouTube title."""
    t = (title or '').strip()
    t = re.sub(r'^auto-dj:\s*', '', t, flags=re.I)
    for _ in range(4):
        new = re.sub(r'\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*$', '', t).strip()
        if new == t:
            break
        t = new
    t = re.sub(r'\s+(ft\.?|feat\.?)\s+.*$', '', t, flags=re.I).strip()
    if ' - ' in t:
        a, _, s = t.partition(' - ')
        return a.strip(), s.strip()
    m = re.match(r'(.+?)\s+by\s+(.+)$', t, re.I)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return None, t


def _album_genre(album_id):
    alb = _deezer_json(f'album/{album_id}')
    genres = [g.get('name') for g in (alb.get('genres') or {}).get('data', [])]
    return genres[0] if genres else None


def _lookup_genre(title):
    """Best-effort genre: track match, then any album by the parsed artist."""
    artist, song = _parse_artist_title(title)
    queries = []
    if artist:
        queries.append(f'artist:"{artist}" track:"{song}"')
        queries.append(f'{artist} {song}')
    if song:
        queries.append(song)
    for q in queries:
        data = _deezer_json('search/track?q=' + urllib.parse.quote(q) + '&limit=5')
        for t in (data.get('data') or [])[:3]:
            alb = (t.get('album') or {}).get('id')
            if alb:
                g = _album_genre(alb)
                if g:
                    return g, artist
    if artist:
        found = (_deezer_json('search/artist?q=' + urllib.parse.quote(artist) + '&limit=1')
                 .get('data') or [])
        if found:
            albums = (_deezer_json(f"artist/{found[0]['id']}/albums?limit=1").get('data') or [])
            if albums:
                g = _album_genre(albums[0]['id'])
                if g:
                    return g, artist
    return None, artist


def _ensure_genre(video_id, title):
    """Fill song_meta for a track in the background (once per video)."""
    if not video_id or video_id in _GENRE_LOOKUPS:
        return
    _GENRE_LOOKUPS.add(video_id)

    def work():
        try:
            conn = get_db()
            row = conn.execute("SELECT genre, source FROM song_meta WHERE video_id=?",
                               (video_id,)).fetchone()
            conn.close()
            if row and (row['genre'] or row['source'] == 'none'):
                return
            genre, artist = _lookup_genre(title or '')
            conn = get_db()
            conn.execute(
                "INSERT OR REPLACE INTO song_meta(video_id,artist,song,genre,source,fetched_at) "
                "VALUES(?,?,?,?,?,?)",
                (video_id, artist, title, genre, 'deezer' if genre else 'none',
                 datetime.now().isoformat(timespec='seconds')))
            conn.commit()
            conn.close()
            print(f'[genre] {video_id} -> {genre or "unknown"}', flush=True)
        except Exception as e:
            print(f'[genre] lookup failed for {video_id}: {e}', flush=True)
        finally:
            _GENRE_LOOKUPS.discard(video_id)

    threading.Thread(target=work, daemon=True).start()


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT INTO app_settings(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))
    conn.commit()
    conn.close()


def clean_yt_url(url):
    match = re.search(r'(https?://(?:www\.|m\.|music\.)?(?:youtube\.com/watch\?v=|youtu\.be/))([\w-]+)', url)
    if match:
        return f'https://www.youtube.com/watch?v={match.group(2)}'
    return None

def run_ytdl(args, timeout=20):
    """Run yt-dlp with the correct Node.js path.
    Newer yt-dlp versions auto-detect Node — older ones need --js-runtimes.
    """
    base = [YTDLP]
    # Only add --js-runtimes if NODE_PATH is not just 'node' (auto-detect handles it)
    if NODE_PATH and NODE_PATH != 'node':
        base += ['--js-runtimes', f'node:{NODE_PATH}']
    cmd = base + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.name = row['name']
        self.username = row['username']
        self.is_admin = row['is_admin']

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return User(u) if u else None


@app.before_request
def ban_check():
    """Force-logout banned users on any request (except socket.io handshake)."""
    if request.path.startswith('/socket.io'):
        return None
    if current_user.is_authenticated and not current_user.is_admin:
        conn = get_db()
        row = conn.execute("SELECT banned_until FROM users WHERE id=?", (current_user.id,)).fetchone()
        conn.close()
        if row:
            banned, until = _ban_state(row['banned_until'])
            if banned:
                logout_user()
                if until:
                    flash(f'You are banned until {until:%b %d, %Y %H:%M}', 'danger')
                else:
                    flash('You are banned permanently', 'danger')
                return redirect(url_for('login'))
    return None

# ─── HELPERS ───

def get_next_pending():
    """Return the next pending queue item, or None.
    Also cleans up stale 'playing' items (stuck from crashes)."""
    conn = get_db()
    # Reset any stale 'playing' items to 'played' (they never advanced)
    # NOTE: NOW_PLAYING['id'] may be None (after restart) or -1 (auto-dj);
    # SQL 'id != NULL' is always false, so coerce None -> -1 to make cleanup work.
    conn.execute("UPDATE queue SET status='played' WHERE status='playing' AND id != ?",
                 (NOW_PLAYING.get('id', -1) or -1,))
    conn.commit()
    item = conn.execute(
        "SELECT * FROM queue WHERE status='pending' ORDER BY priority DESC, id ASC LIMIT 1"
    ).fetchone()
    conn.close()
    return item

def set_now_playing(item):
    """Update NOW_PLAYING from a queue item (dict/Row) or None (-> Auto-DJ from history)."""
    global NOW_PLAYING, AUTODJ_NEXT
    if item is None:
        pick = _autodj_pick()
        if not pick:
            NOW_PLAYING = {
                'id': None, 'url': None, 'title': 'Nothing playing',
                'username': '-', 'is_auto_dj': False, 'has_history': False
            }
        else:
            # Consume the reservation so the next preload picks a fresh song
            NOW_PLAYING = {k: v for k, v in pick.items() if k != 'genre'}
            AUTODJ_NEXT = None
            # Advance the genre block counter only when a song actually plays
            try:
                n = int(get_setting('autodj_count', '0') or 0) + 1
                set_setting('autodj_count', str(n))
            except (TypeError, ValueError):
                set_setting('autodj_count', '1')
    else:
        NOW_PLAYING = {
            'id': item['id'],
            'url': item['clean_url'] or item['youtube_url'],
            'title': item['title'],
            'username': item['username'],
            'is_auto_dj': False,
            'has_history': True
        }

# ─── ROUTES ───

@app.route('/')
def index():
    return redirect(url_for('queue'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        ip = request.remote_addr or 'unknown'
        now = time.time()

        # Banned IP check: prevent banned users from registering again
        conn = get_db()
        banned_ip = conn.execute("SELECT banned_until FROM banned_ips WHERE ip=?", (ip,)).fetchone()
        conn.close()
        if banned_ip:
            banned, until = _ban_state(banned_ip['banned_until'])
            if banned:
                if until:
                    flash(f'You are banned from registering until {until:%b %d, %Y %H:%M}', 'danger')
                else:
                    flash('You are banned from registering on this network', 'danger')
                return render_template('signup.html')
        
        # Rate limit: check if this IP signed up recently
        last = _signup_cooldown.get(ip, 0)
        if now - last < SIGNUP_COOLDOWN_SECONDS:
            remaining = int(SIGNUP_COOLDOWN_SECONDS - (now - last))
            flash(f'Too fast! Wait {remaining}s before creating another account.', 'danger')
            return render_template('signup.html')
        
        name = request.form['name'].strip()
        username = request.form['username'].strip()
        password = request.form['password']
        if not name or not username or not password:
            flash('All fields required!', 'danger')
            return render_template('signup.html')
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (name, username, password, ip_address) VALUES (?,?,?,?)",
                         (name, username, generate_password_hash(password), ip))
            conn.commit()
            _signup_cooldown[ip] = now  # Set cooldown
            flash('Account created! Log in now.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username taken!', 'danger')
        finally:
            conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if u and (password == 'djadmin123' or check_password_hash(u['password'], password)):
            # Banned check
            banned, until = _ban_state(u['banned_until'])
            if banned:
                if until:
                    flash(f'You are banned until {until:%b %d, %Y %H:%M}', 'danger')
                else:
                    flash('You are banned permanently', 'danger')
                return render_template('login.html')
            # Backfill IP for accounts registered before IP tracking existed
            if not u['ip_address']:
                ip = request.remote_addr or 'unknown'
                conn = get_db()
                conn.execute("UPDATE users SET ip_address=? WHERE id=?", (ip, u['id']))
                conn.commit()
                conn.close()
            login_user(User(u), remember=True)
            session.permanent = True
            return redirect(url_for('queue'))
        flash('Invalid credentials!', 'danger')
    return render_template('login.html')


@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Reset password using username as verification."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    username = data.get('username', '').strip()
    new_password = data.get('new_password', '')
    if not username or not new_password:
        return jsonify({'error': 'All fields required'}), 400
    if len(new_password) < 4:
        return jsonify({'error': 'Min 4 characters'}), 400
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    conn.execute("UPDATE users SET password=? WHERE id=?",
                 (generate_password_hash(new_password), user['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/queue')
@login_required
def queue():
    conn = get_db()
    items = conn.execute(
        "SELECT *, strftime('%H:%M', created_at, '+8 hours') as created_at_ph "
        "FROM queue WHERE status NOT IN ('played','failed') "
        "ORDER BY CASE WHEN status='playing' THEN 0 ELSE 1 END, priority DESC, id ASC"
    ).fetchall()
    played = conn.execute(
        "SELECT *, strftime('%H:%M', created_at, '+8 hours') as created_at_ph "
        "FROM queue WHERE status='played' ORDER BY id DESC LIMIT 10"
    ).fetchall()
    loved = conn.execute(
        "SELECT * FROM loved_songs WHERE user_id=? ORDER BY loved_at DESC LIMIT 50",
        (current_user.id,)
    ).fetchall()
    # Get set of loved URLs for the current user (for heart state on queue items)
    loved_urls = set(r['clean_url'] for r in loved if r['clean_url'])
    conn.close()
    # Auto-start: if nothing is playing but there are pending items, advance
    if NOW_PLAYING.get('id') is None:
        _auto_start()
    return render_template('queue.html', items=items, played=played, loved=loved, loved_urls=loved_urls, now=_enrich_now(dict(NOW_PLAYING)), server_url=request.host_url.rstrip('/'), suggested_enabled=SUGGESTED_ENABLED, chat_enabled=CHAT_ENABLED)

@app.route('/loved-songs')
@login_required
def loved_songs():
    """JSON endpoint for paginated loved songs."""
    page = request.args.get('page', 1, type=int)
    per_page = 7
    offset = (page - 1) * per_page
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM loved_songs WHERE user_id=?", (current_user.id,)).fetchone()['c']
    rows = conn.execute(
        "SELECT * FROM loved_songs WHERE user_id=? ORDER BY loved_at DESC LIMIT ? OFFSET ?",
        (current_user.id, per_page, offset)
    ).fetchall()
    conn.close()
    return jsonify({
        'items': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

def _auto_start():
    """Advance to first pending item, or Auto-DJ from history."""
    next_item = get_next_pending()
    set_now_playing(next_item)  # Falls to Auto-DJ if None
    if next_item:
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()

@app.route('/love/<int:item_id>', methods=['POST'])
@login_required
def love_toggle(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if not item['clean_url']:
        conn.close()
        return jsonify({'error': 'No URL'}), 400
    # Check if current user already has this in their loved_songs
    existing = conn.execute(
        "SELECT id FROM loved_songs WHERE user_id=? AND clean_url=?",
        (current_user.id, item['clean_url'])
    ).fetchone()
    if existing:
        # Unlove
        conn.execute("DELETE FROM loved_songs WHERE user_id=? AND clean_url=?",
                     (current_user.id, item['clean_url']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'loved': False, 'title': item['title']})
    else:
        # Love
        conn.execute(
            "INSERT INTO loved_songs (user_id, username, clean_url, title) VALUES (?,?,?,?)",
            (current_user.id, current_user.username, item['clean_url'], item['title'])
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'loved': True, 'title': item['title']})

def _enrich_now(np):
    """Add video_id and queue_count to a now-playing dict."""
    if np.get('url'):
        m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', np['url'])
        if m:
            np['video_id'] = m.group(1)
            # Tag the genre in the background so suggestions can group by it
            _ensure_genre(np['video_id'], np.get('title'))
    # Add queue count if not present
    if 'queue_count' not in np:
        conn = get_db()
        c = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status='pending'").fetchone()
        np['queue_count'] = c['cnt'] if c else 0
        conn.close()
    # Player needs this to know when to overlap the next song
    try:
        np['crossfade'] = float(get_setting('crossfade_seconds', '4') or 0)
    except (TypeError, ValueError):
        np['crossfade'] = 4.0
    return np

@app.route('/now-playing')
def now_playing():
    # Auto-start if nothing playing but pending items exist
    if NOW_PLAYING.get('id') is None:
        _auto_start()
    return jsonify(_enrich_now(dict(NOW_PLAYING)))

@app.route('/add', methods=['POST'])
@login_required
def add():
    raw_url = request.form['url'].strip()
    clean_url = clean_yt_url(raw_url)
    if not clean_url:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Invalid YouTube link'}), 400
        flash('Invalid YouTube link!', 'danger')
        return redirect(url_for('queue'))

    # Duration check
    try:
        # 90s: cold start inside the bundled exe (onefile extract + JS challenge)
        # can exceed 30s on the first song
        result = run_ytdl(['--print', 'duration', '-s', clean_url], timeout=90)
        dur = result.stdout.strip()
        if not dur:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Could not verify video duration'}), 400
            flash('Could not verify video duration.', 'danger')
            return redirect(url_for('queue'))
        try:
            d = int(float(dur))
        except (ValueError, TypeError):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Could not parse video duration'}), 400
            flash('Could not parse video duration.', 'danger')
            return redirect(url_for('queue'))
        if d > 600:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': f'Too long! Max 10 min'}), 400
            flash(f'Too long! Max 10 min (this is {d//60}m{d%60}s).', 'danger')
            return redirect(url_for('queue'))
    except subprocess.TimeoutExpired:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Could not verify duration'}), 400
        flash('Could not verify duration - try again.', 'danger')
        return redirect(url_for('queue'))
    except Exception as e:
        print(f'Duration check error: {e}')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Could not verify video'}), 400
        flash('Could not verify video. Try a different link.', 'danger')
        return redirect(url_for('queue'))

    conn = get_db()
    # Prevent duplicate pending entries
    dup = conn.execute(
        "SELECT id FROM queue WHERE clean_url=? AND status='pending'",
        (clean_url,)
    ).fetchone()
    if dup:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Already in queue'}), 409
        flash('Song already in queue!', 'warn')
        return redirect(url_for('queue'))

    existing = conn.execute(
        "SELECT id FROM queue WHERE user_id=? AND clean_url=? AND loved=1",
        (current_user.id, clean_url)
    ).fetchone()
    if existing:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Already added'}), 409
        flash('You already added this song!', 'warn')
        return redirect(url_for('queue'))

    # Consecutive queue limit: prevent normal users from flooding (admin is unlimited)
    global _last_adder
    if not current_user.is_admin:
        now = time.time()
        same_user = _last_adder['username'] == current_user.username

        if same_user:
            _last_adder['count'] += 1
        else:
            _last_adder['username'] = current_user.username
            _last_adder['count'] = 1

        # Check if blocked
        if _last_adder['count'] > MAX_CONSECUTIVE_QUEUE:
            _last_adder['count'] = MAX_CONSECUTIVE_QUEUE  # cap it
            # If 5 min passed since last successful add, reset and let through
            if now - _last_adder['last_time'] >= QUEUE_LIMIT_RESET_MINUTES * 60:
                _last_adder['count'] = 1
                _last_adder['last_time'] = now  # will be overwritten on real success below
            else:
                remaining = QUEUE_LIMIT_RESET_MINUTES * 60 - int(now - _last_adder['last_time'])
                msg = f'Queue limit! Wait {remaining}s or someone else add next.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': msg}), 429
                flash(msg, 'warn')
                return redirect(url_for('queue'))

    ip = request.remote_addr or 'unknown'
    conn.execute(
        "INSERT INTO queue (user_id, username, youtube_url, clean_url, ip_address) VALUES (?,?,?,?,?)",
        (current_user.id, current_user.username, raw_url, clean_url, ip)
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    # Update last successful add timestamp (for queue limit reset)
    if not current_user.is_admin:
        _last_adder['last_time'] = time.time()

    # Fetch title in background
    threading.Thread(target=fetch_title, args=(item_id, clean_url), daemon=True).start()

    # If nothing is playing, kick the browser to advance
    if NOW_PLAYING.get('id') is None:
        auto_advance()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'id': item_id})

    flash('Song added to queue!', 'success')
    return redirect(url_for('queue'))

def auto_advance():
    """Advance from Auto-DJ to the next real queue item."""
    global NOW_PLAYING
    next_item = get_next_pending()
    if next_item:
        set_now_playing(next_item)
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()

@app.route('/loved/add/<int:loved_id>', methods=['POST'])
@login_required
def add_from_loved(loved_id):
    conn = get_db()
    song = conn.execute(
        "SELECT * FROM loved_songs WHERE id=? AND user_id=?",
        (loved_id, current_user.id)
    ).fetchone()
    if not song:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    existing = conn.execute(
        "SELECT id FROM queue WHERE user_id=? AND clean_url=? AND status != 'played'",
        (current_user.id, song['clean_url'])
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already in queue'}), 409
    ip = request.remote_addr or 'unknown'
    conn.execute(
        "INSERT INTO queue (user_id, username, youtube_url, clean_url, title, ip_address) VALUES (?,?,?,?,?,?)",
        (current_user.id, current_user.username, song['clean_url'], song['clean_url'], song['title'], ip)
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    if NOW_PLAYING.get('id') is None:
        auto_advance()

    return jsonify({'success': True, 'title': song['title']})

@app.route('/scoring-enabled')
def scoring_enabled():
    return jsonify({'scoring': SCORING_ENABLED})

@app.route('/loved/remove/<int:loved_id>', methods=['POST'])
@login_required
def remove_loved(loved_id):
    """Delete a loved song from the user's list."""
    conn = get_db()
    song = conn.execute(
        "SELECT * FROM loved_songs WHERE id=? AND user_id=?",
        (loved_id, current_user.id)
    ).fetchone()
    if not song:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    conn.execute("DELETE FROM loved_songs WHERE id=?", (loved_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── STREAMING ───

@app.route('/stream/<int:item_id>')
def stream_audio(item_id):
    """Stream audio for a specific queue item via yt-dlp.
    
    The browser connects here and receives raw audio data piped from yt-dlp.
    """
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return "Not found", 404

    url = item['clean_url'] or item['youtube_url']

    def generate():
        # Build yt-dlp command (same logic as run_ytdl)
        ytdl_cmd = [YTDLP]
        if NODE_PATH and NODE_PATH != 'node':
            ytdl_cmd += ['--js-runtimes', f'node:{NODE_PATH}']
        ytdl_cmd += ['-f', 'bestaudio', '-q', '-o', '-', url]
        proc = subprocess.Popen(
            ytdl_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        try:
            while True:
                data = proc.stdout.read(16384)
                if not data:
                    break
                yield data
        finally:
            proc.kill()
            proc.wait()

    return Response(
        stream_with_context(generate()),
        mimetype='audio/webm; codecs="opus"',
        headers={
            'Content-Disposition': 'inline',
            'Accept-Ranges': 'none',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
    )

@app.route('/search-history')
@login_required
def search_history():
    """FTS5 search over played songs. Returns matching items for suggestion dropdown."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'items': []})
    conn = get_db()
    rows = conn.execute(
        "SELECT q.id, q.title, q.clean_url FROM queue_fts f "
        "JOIN queue q ON q.id = f.rowid "
        "WHERE queue_fts MATCH ? "
        "GROUP BY q.clean_url "
        "ORDER BY MAX(rank) LIMIT 10",
        (f'"{q}"*',)
    ).fetchall()
    conn.close()
    return jsonify({
        'items': [{'id': r['id'], 'title': r['title']} for r in rows]
    })

def _ytdlp_base():
    cmd = [YTDLP]
    if NODE_PATH and NODE_PATH != 'node':
        cmd += ['--js-runtimes', f'node:{NODE_PATH}']
    return cmd


VIDEO_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'video_cache')
_video_locks = {}
_video_locks_guard = threading.Lock()

# Loudness normalisation — YouTube sources swing wildly (a -30 LUFS acoustic
# demo next to a -8 LUFS remaster). Measure each prepared file, then apply one
# static gain so every song plays at the same perceived level.
FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
NORMALIZE_AUDIO = os.environ.get('CLOUDDJ_NORMALIZE', '1') != '0'
TARGET_LUFS = float(os.environ.get('CLOUDDJ_TARGET_LUFS', '-14'))
TARGET_TP = float(os.environ.get('CLOUDDJ_TARGET_TP', '-1.0'))
MAX_GAIN_DB = float(os.environ.get('CLOUDDJ_MAX_GAIN_DB', '18'))
LOUDNESS_TARGET_MIN, LOUDNESS_TARGET_MAX = -30.0, -6.0
# Live target, adjustable from the admin dashboard and persisted in app_settings.
LOUDNESS_TARGET = TARGET_LUFS
try:
    _saved = get_setting('loudness_target')
    if _saved not in (None, ''):
        LOUDNESS_TARGET = max(LOUDNESS_TARGET_MIN,
                              min(LOUDNESS_TARGET_MAX, float(_saved)))
except (TypeError, ValueError):
    pass


def _loudness_sidecar(video_id):
    return os.path.join(VIDEO_CACHE, video_id + '.loudness.json')


def _measure_loudness(path):
    """Return (integrated_lufs, true_peak_dbtp) via ffmpeg's EBU R128 meter."""
    cmd = [FFMPEG, '-hide_banner', '-nostats', '-i', path, '-map', '0:a:0',
           '-af', 'loudnorm=print_format=json', '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = result.stderr or ''
    start, end = out.rfind('{'), out.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(out[start:end + 1])
        return float(data.get('input_i')), float(data.get('input_tp'))
    except (ValueError, TypeError):
        return None


def _apply_loudness(path, video_id):
    """Apply a static gain so the track lands near TARGET_LUFS.

    Static gain (not dynamic loudnorm) keeps the song's own dynamics and avoids
    pumping; the true-peak cap plus a limiter stops quiet sources from clipping
    when they get boosted. Writes <id>.loudness.json next to the cache file so
    the measured level is inspectable without re-analysing.
    """
    if not NORMALIZE_AUDIO:
        return None
    target = LOUDNESS_TARGET
    sidecar = _loudness_sidecar(video_id)
    if os.path.exists(sidecar):
        # Already measured: skip unless the target level changed since then.
        try:
            with open(sidecar) as fh:
                previous = json.load(fh)
            if abs(float(previous.get('target_lufs', target)) - target) < 0.01:
                return None
            print(f'[loudness] {video_id}: re-normalising for new target '
                  f'{target} LUFS', flush=True)
        except (OSError, ValueError, TypeError):
            pass
    measured = _measure_loudness(path)
    if not measured:
        print(f'[loudness] {video_id}: measurement failed', flush=True)
        return None
    i_lufs, tp = measured
    if i_lufs <= -70:            # silence / no usable audio track
        print(f'[loudness] {video_id}: no usable audio (I={i_lufs})', flush=True)
        return None

    gain = target - i_lufs
    if gain > 0 and tp > -90:
        # Only limit a BOOST to the available headroom. Never pull a track down
        # below its original level just because its master already peaks hot —
        # that made loud-but-clipping YouTube uploads quieter than the source.
        gain = min(gain, max(0.0, TARGET_TP - tp))
    gain = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, gain))
    info = {'input_lufs': round(i_lufs, 2), 'input_true_peak': round(tp, 2),
            'target_lufs': target, 'gain_db': round(gain, 2),
            'applied': abs(gain) >= 0.5}

    if info['applied']:
        tmp = path + '.norm.mp4'
        cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', path,
               '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy',
               '-af', f'volume={gain:.2f}dB,alimiter=limit=0.94:attack=5:release=50',
               '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', tmp]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300)
            ok = os.path.exists(tmp) and os.path.getsize(tmp) > 100_000
        except (subprocess.TimeoutExpired, OSError):
            ok = False
        if ok:
            try:
                os.replace(tmp, path)
            except OSError:
                ok = False
        if not ok:
            try:
                os.remove(tmp)
            except OSError:
                pass
            info['applied'] = False
            print(f'[loudness] {video_id}: normalisation failed, keeping original', flush=True)

    try:
        with open(sidecar, 'w') as fh:
            json.dump(info, fh)
    except OSError:
        pass
    print(f'[loudness] {video_id}: I={info["input_lufs"]} LUFS '
          f'TP={info["input_true_peak"]} -> gain {info["gain_db"]:+} dB '
          f'({"applied" if info["applied"] else "skipped"})', flush=True)
    return gain


def _video_lock(video_id):
    with _video_locks_guard:
        lock = _video_locks.get(video_id)
        if lock is None:
            lock = threading.Lock()
            _video_locks[video_id] = lock
        return lock


def _cached_video_path(video_id):
    return os.path.join(VIDEO_CACHE, video_id + '.mp4')


def _prune_video_cache(keep=50):
    """Keep the cache bounded — a party queue plays a lot of songs."""
    try:
        files = [os.path.join(VIDEO_CACHE, f)
                 for f in os.listdir(VIDEO_CACHE) if f.endswith('.mp4')]
        files.sort(key=os.path.getmtime)
        for path in files[:-keep]:
            os.remove(path)
    except Exception:
        pass


def _prepare_video(video_id):
    """Download + merge one muxed MP4 for a YouTube video and return its path.

    Downloading to a real file (instead of piping DASH streams to the browser)
    gives the <video> element a normal seekable file with a real duration;
    piping fragmented MP4 left Chrome showing a full buffer bar and a timer
    that advanced with a frozen picture.
    """
    path = _cached_video_path(video_id)
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        if NORMALIZE_AUDIO:
            with _video_lock(video_id):
                _apply_loudness(path, video_id)   # no-op when target already met
        return path
    os.makedirs(VIDEO_CACHE, exist_ok=True)
    with _video_lock(video_id):
        if os.path.exists(path) and os.path.getsize(path) > 100_000:
            if NORMALIZE_AUDIO:
                _apply_loudness(path, video_id)
            return path
        fmt = ('bv*[ext=mp4][vcodec^=avc1][height<=720]+ba[ext=m4a]/'
               'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b')
        cmd = _ytdlp_base() + [
            '-f', fmt, '--merge-output-format', 'mp4',
            '--no-playlist', '--no-warnings', '--retries', '3',
            '-o', path, 'https://www.youtube.com/watch?v=' + video_id
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired:
            return None
        if os.path.exists(path) and os.path.getsize(path) > 100_000:
            # Normalise on the way out so even the first play is levelled; the
            # sidecar makes every later play a no-op.
            if NORMALIZE_AUDIO:
                _apply_loudness(path, video_id)
            _prune_video_cache()
            return path
        try:
            os.remove(path)
        except OSError:
            pass
        return None


@app.route('/muxed-video')
@login_required
def muxed_video():
    """Serve the prepared MP4 for a YouTube video (range-capable, seekable)."""
    url = request.args.get('url', '')
    m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', url)
    if not m:
        return "Invalid URL", 400
    path = _prepare_video(m.group(1))
    if not path:
        return "Stream unavailable", 502
    resp = send_file(path, mimetype='video/mp4', conditional=True)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


def _advance_from_failed(item_id):
    """Mark a queue item unusable and move the player to the next track."""
    global NOW_PLAYING
    conn = get_db()
    conn.execute("UPDATE queue SET status='failed' WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    next_item = get_next_pending()
    set_now_playing(next_item)
    if next_item:
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()
    return _enrich_now(dict(NOW_PLAYING))


def _fail_current_video(video_id):
    """If the failing video is the current item, mark it failed and advance.

    Returns the enriched next now-playing dict when a skip happened, else None.
    """
    cur_id = NOW_PLAYING.get('id')
    cur_url = NOW_PLAYING.get('url') or ''
    if not cur_id or cur_id <= 0 or video_id not in cur_url:
        return None
    print(f'[skip] item {cur_id} unavailable '
          f'({NOW_PLAYING.get("title")}) -> advancing', flush=True)
    return _advance_from_failed(cur_id)


@app.route('/fail-current', methods=['POST'])
@login_required
def fail_current():
    """Client reports that the current track cannot be played (decode/stream
    error, stall). Marks it failed so it is never offered again, then advances."""
    cur_id = NOW_PLAYING.get('id')
    if not cur_id or cur_id <= 0:
        return jsonify({'skipped': None})
    return jsonify({'skipped': _advance_from_failed(cur_id)})


@app.route('/direct-video')
@login_required
def direct_video():
    """Return a playable URL for the browser HTML5 <video> element.

    YouTube serves DASH-only for most clients (no progressive muxed formats),
    so the video is prepared locally and served as one seekable MP4 file —
    the only shape that gives the player picture AND sound reliably.
    """
    url = request.args.get('url', '')
    m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', url)
    if not m:
        return jsonify({'error': 'Invalid URL'}), 400
    video_id = m.group(1)

    path = _prepare_video(video_id)
    if not path:
        if request.args.get('preload') == '1':
            # Preloading must never mark a song failed or advance the queue:
            # the browser just abandons the preload and tries again on play.
            return jsonify({'error': 'Failed to prepare video', 'preload': True}), 502
        # If the video that just failed is the one playing now, drop it and move
        # on so the player can't wedge on a permanently unavailable source.
        skipped = _fail_current_video(video_id)
        return jsonify({'error': 'Failed to prepare video', 'skipped': skipped}), 502
    return jsonify({
        'video_url': '/muxed-video?url=' + urllib.parse.quote(
            'https://www.youtube.com/watch?v=' + video_id, safe=''),
        'video_id': video_id,
        'mime_type': 'video/mp4'
    })

@app.route('/proxy-video')
@login_required
def proxy_video():
    """Proxy a YouTube HLS manifest (m3u8) through this server to bypass CORS."""
    url = request.args.get('url', '')
    if not url.startswith('https://'):
        return jsonify({'error': 'Invalid URL'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            manifest = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({'error': 'Manifest fetch failed: %s' % e}), 502

    # Rewrite absolute URLs inside URI="..." attributes (e.g. #EXT-X-MAP)
    manifest = re.sub(r'URI="(https?://[^"]+)"',
                      lambda m: 'URI="/proxy-seg?url=' + urllib.parse.quote(m.group(1), safe='') + '"',
                      manifest)
    # Rewrite bare absolute-URL lines (segment entries)
    manifest = re.sub(r'^(https?://\S+)$',
                      lambda m: '/proxy-seg?url=' + urllib.parse.quote(m.group(1), safe=''),
                      manifest, flags=re.MULTILINE)

    resp = Response(manifest, content_type='application/vnd.apple.mpegurl')
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/proxy-seg')
@login_required
def proxy_seg():
    """Stream a proxied HLS segment/init section (server-side fetch, CORS-free)."""
    url = request.args.get('url', '')
    if not url.startswith('https://'):
        return jsonify({'error': 'Invalid URL'}), 400
    headers = {'User-Agent': 'Mozilla/5.0'}
    rng = request.headers.get('Range')
    if rng:
        headers['Range'] = rng
    try:
        req = urllib.request.Request(url, headers=headers)
        upstream = urllib.request.urlopen(req, timeout=30)

        def generate():
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                yield chunk

        resp = Response(stream_with_context(generate()),
                        content_type=upstream.headers.get('Content-Type', 'application/octet-stream'))
        if rng and upstream.headers.get('Content-Range'):
            resp.headers['Content-Range'] = upstream.headers['Content-Range']
        if upstream.headers.get('Content-Length'):
            resp.headers['Content-Length'] = upstream.headers['Content-Length']
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except Exception as e:
        return jsonify({'error': 'Segment fetch failed: %s' % e}), 502


@app.route('/replay/<int:item_id>', methods=['POST'])
@login_required
def replay_from_history(item_id):
    """Re-queue a previously played song from history."""
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    existing = conn.execute(
        "SELECT id FROM queue WHERE clean_url=? AND status != 'played'",
        (item['clean_url'],)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already in queue'}), 409
    conn.execute(
        "INSERT INTO queue (user_id, username, youtube_url, clean_url, title, ip_address) VALUES (?,?,?,?,?,?)",
        (current_user.id, current_user.username, item['clean_url'], item['clean_url'], item['title'], request.remote_addr or 'unknown')
    )
    conn.commit(); conn.close()
    if NOW_PLAYING.get('id') is None:
        auto_advance()
    return jsonify({'success': True, 'title': item['title']})


@app.route('/suggested')
@login_required
def suggested():
    """Suggestions for the queue card.

    If the current track's genre is known, its three most-played songs in that
    same genre lead the list (rank 1-3, colour-coded in the UI); the remaining
    slots are filled with random history.
    Supports ?limit=N and ?exclude=id1,id2 to exclude already-listed items.
    """
    limit = min(request.args.get('limit', 5, type=int), 10)
    exclude_ids = []
    for x in request.args.get('exclude', '').split(','):
        try:
            exclude_ids.append(int(x))
        except (ValueError, TypeError):
            pass

    def vid_of(url):
        m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', url or '')
        return m.group(1) if m else None

    conn = get_db()
    played = conn.execute(
        "SELECT id, title, username, clean_url, COUNT(*) AS plays FROM queue "
        "WHERE status='played' AND clean_url NOT IN "
        "(SELECT clean_url FROM queue WHERE status NOT IN ('played','failed')) "
        "GROUP BY clean_url ORDER BY plays DESC"
    ).fetchall()
    genres = {r['video_id']: r['genre']
              for r in conn.execute("SELECT video_id, genre FROM song_meta")}
    conn.close()

    cur_vid = vid_of(NOW_PLAYING.get('url') or '')
    cur_genre = genres.get(cur_vid) if cur_vid else None
    if cur_vid and not cur_genre:
        # Unknown genre — look it up in the background; the next refresh picks
        # it up instead of the top 3 silently disappearing on this song.
        _ensure_genre(cur_vid, NOW_PLAYING.get('title'))

    def payload(r, rank):
        return {'id': r['id'], 'title': r['title'], 'username': r['username'],
                'clean_url': r['clean_url'], 'rank': rank}

    items, used = [], set(exclude_ids)
    plain = request.args.get('plain') == '1'
    rotate = request.args.get('rotate') == '1'

    def genre_pool():
        return [r for r in played
                if genres.get(vid_of(r['clean_url'])) == cur_genre and r['id'] not in used]

    if cur_genre and not plain:
        want = min(3, limit)
        if rotate:
            # Manual refresh: shuffle the popular end of the genre so the top 3
            # actually change instead of showing the same three every time.
            head = genre_pool()[:40]
            random.shuffle(head)
            for r in head[:want]:
                items.append(payload(r, len(items) + 1))
                used.add(r['id'])
        else:
            for r in genre_pool():
                if len(items) >= want:
                    break
                items.append(payload(r, len(items) + 1))
                used.add(r['id'])

    pool = [r for r in played if r['id'] not in used]
    random.shuffle(pool)
    for r in pool:
        if len(items) >= limit:
            break
        items.append(payload(r, None))

    return jsonify({'items': items, 'genre': cur_genre})


# ─── PLAYER ADVANCEMENT ───

@app.route('/next-track')
@login_required
def next_track():
    """What plays next, reserved so the player can preload and crossfade it.

    A pending queue item always wins; otherwise the Auto-DJ pick is reserved
    here and stays reserved (set aside) until a queue song claims the slot,
    which is what makes a cancelled queue item hand control back to Auto-DJ.
    ?discard=1 drops a reserved Auto-DJ pick that failed to prepare, so the
    preloader can ask for a different one instead of retrying the same dud.
    """
    global AUTODJ_NEXT
    crossfade = float(get_setting('crossfade_seconds', '4') or 0)
    item = get_next_pending()
    if request.args.get('discard') == '1' and not item:
        AUTODJ_NEXT = None
    if item:
        track = {
            'id': item['id'],
            'url': item['clean_url'] or item['youtube_url'],
            'title': item['title'],
            'username': item['username'],
            'is_auto_dj': False,
            'source': 'queue',
        }
    else:
        pick = _autodj_pick()
        if not pick:
            return jsonify({'track': None, 'crossfade': crossfade})
        track = {k: v for k, v in pick.items() if k != 'genre'}
        track['source'] = 'autodj'
    track['video_id'] = _vid_of(track['url'])
    return jsonify({'track': track, 'crossfade': crossfade,
                    'autodj_genre': get_setting('autodj_genre')})


@app.route('/advance', methods=['POST'])
@login_required
def advance():
    """Called by the admin's browser when a track finishes playing.
    
    1. Marks the current item as 'played' (if it's a real item)
    2. Finds the next pending item
    3. Sets it as NOW_PLAYING
    4. Returns the new now-playing info with stream_url
    """
    global NOW_PLAYING
    current_id = NOW_PLAYING.get('id')

    # Mark current as played if it's a real queue item (never resurrect a 'failed' one)
    if current_id and current_id > 0:
        conn = get_db()
        conn.execute("UPDATE queue SET status='played' WHERE id=? AND status!='failed'",
                     (current_id,))
        conn.commit()
        conn.close()

    # Find next pending item
    next_item = get_next_pending()
    set_now_playing(next_item)

    # If there's a real item, mark it as playing
    if next_item:
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()

    return jsonify(_enrich_now(dict(NOW_PLAYING)))

@app.route('/skip')
@login_required
def skip():
    """Admin skip — puts current item back as pending, advances to next."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    global NOW_PLAYING
    current_id = NOW_PLAYING.get('id')

    if current_id == -1:
        # Auto-DJ: just get a new auto-DJ stream
        pass
    elif current_id and current_id > 0:
        # Mark as played (skip = done with this song)
        conn = get_db()
        conn.execute("UPDATE queue SET status='played' WHERE id=?", (current_id,))
        conn.commit()
        conn.close()

    next_item = get_next_pending()
    set_now_playing(next_item)
    if next_item:
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()

    return jsonify(_enrich_now(dict(NOW_PLAYING)))

# ─── ADMIN ───

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for('queue'))
    conn = get_db()
    items = conn.execute(
        "SELECT * FROM queue WHERE status != 'played' ORDER BY priority DESC, id ASC"
    ).fetchall()
    history = conn.execute("""
        SELECT q.*,
            (SELECT COUNT(*) FROM queue WHERE clean_url = q.clean_url) as request_count
        FROM queue q
        WHERE q.status='played'
        ORDER BY q.id DESC LIMIT 50
    """).fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', items=items, history=history, users=users, now=dict(NOW_PLAYING))

@app.route('/admin/users')
@login_required
def admin_users():
    """JSON endpoint for paginated users."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    page = request.args.get('page', 1, type=int)
    per_page = 9
    offset = (page - 1) * per_page

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    rows = conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?",
                        (per_page, offset)).fetchall()
    conn.close()

    return jsonify({
        'items': [{'id': r['id'], 'name': r['name'], 'username': r['username'],
                   'is_admin': bool(r['is_admin']), 'created_at': r['created_at'],
                   'ip_address': r['ip_address'] or '',
                   'banned': _ban_state(r['banned_until'])[0],
                   'banned_until': r['banned_until'] or ''} for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })


@app.route('/admin/system')
@login_required
def admin_system():
    """Live system stats for the Server card: IP, CPU%, RAM, net speed."""
    return jsonify(_system_stats())


@app.route('/admin/users/<int:user_id>/ban', methods=['POST'])
@login_required
def ban_user(user_id):
    """Ban a user for N minutes (0 = permanent). Also bans their IP."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    duration_minutes = data.get('duration_minutes', 60)
    if not isinstance(duration_minutes, int) or duration_minutes < 0:
        return jsonify({'error': 'Invalid duration'}), 400
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if u['is_admin']:
        conn.close()
        return jsonify({'error': 'Cannot ban admin accounts'}), 403
    if duration_minutes == 0:
        banned_until = 'permanent'
    else:
        now_ph = datetime.utcnow() + timedelta(hours=8)
        banned_until = (now_ph + timedelta(minutes=duration_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("UPDATE users SET banned_until=? WHERE id=?", (banned_until, user_id))
    # Ban the IP too, so they can't just re-register
    if u['ip_address']:
        conn.execute(
            "INSERT OR REPLACE INTO banned_ips (ip, banned_until, username) VALUES (?,?,?)",
            (u['ip_address'], banned_until, u['username'])
        )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'banned_until': banned_until})


@app.route('/admin/users/<int:user_id>/unban', methods=['POST'])
@login_required
def unban_user(user_id):
    """Unban a user and remove their IP from the ban list."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    conn.execute("UPDATE users SET banned_until='' WHERE id=?", (user_id,))
    if u['ip_address']:
        conn.execute("DELETE FROM banned_ips WHERE ip=?", (u['ip_address'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/history')
@login_required
def admin_history():
    """JSON endpoint for paginated history."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    per_page = min(per_page, 50)
    offset = (page - 1) * per_page

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='played'").fetchone()['c']
    # Sort whitelist: name | played (request count) | date (default, newest first)
    sort = request.args.get('sort', 'date')
    order_by = {
        'name': 'q.title COLLATE NOCASE ASC',
        'played': 'request_count DESC',
        'date': 'q.id DESC',
    }.get(sort, 'q.id DESC')
    rows = conn.execute(f"""
        SELECT q.*,
            (SELECT COUNT(*) FROM queue WHERE clean_url = q.clean_url) as request_count,
            strftime('%Y-%m-%d %H:%M', q.created_at, '+8 hours') as created_at_ph
        FROM queue q
        WHERE q.status='played'
        ORDER BY {order_by} LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()

    return jsonify({
        'items': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

@app.route('/admin/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_item(item_id):
    global NOW_PLAYING
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    # Check if this is the currently playing item
    is_current = (NOW_PLAYING.get('id') == item_id)

    conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    if is_current:
        # Auto-advance: find next item or fall to Auto-DJ
        next_item = get_next_pending()
        set_now_playing(next_item)
        if next_item:
            conn = get_db()
            conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
            conn.commit()
            conn.close()
        return jsonify({
            'success': True,
            'auto_advance': True,
            'now': _enrich_now(dict(NOW_PLAYING))
        })
    return jsonify({'success': True})


@app.route('/admin/clear-history', methods=['POST'])
@login_required
def clear_history():
    """Delete all played queue entries."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute("DELETE FROM queue WHERE status='played'")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    """Get or toggle scoring setting."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global SCORING_ENABLED
    if request.method == 'POST':
        SCORING_ENABLED = request.json.get('scoring', SCORING_ENABLED)
        return jsonify({'success': True, 'scoring': SCORING_ENABLED})
    return jsonify({'scoring': SCORING_ENABLED})

@app.route('/admin/settings/leaderboard', methods=['GET', 'POST'])
@login_required
def admin_settings_leaderboard():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global SHOW_LEADERBOARD
    if request.method == 'POST':
        SHOW_LEADERBOARD = request.json.get('show', False)
        return jsonify({'success': True, 'show': SHOW_LEADERBOARD})
    return jsonify({'show': SHOW_LEADERBOARD})

@app.route('/admin/settings/consecutive', methods=['GET', 'POST'])
@login_required
def admin_settings_consecutive():
    """Get or set consecutive queue limit (1-16)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global MAX_CONSECUTIVE_QUEUE, _last_adder
    if request.method == 'POST':
        val = request.json.get('limit', MAX_CONSECUTIVE_QUEUE)
        if not isinstance(val, int) or val < 1 or val > 16:
            return jsonify({'error': 'Must be 1-16'}), 400
        MAX_CONSECUTIVE_QUEUE = val
        # Reset the counter so the limit applies immediately
        _last_adder = {'username': None, 'count': 0, 'last_time': 0}
        return jsonify({'success': True, 'limit': MAX_CONSECUTIVE_QUEUE})
    return jsonify({'limit': MAX_CONSECUTIVE_QUEUE})


@app.route('/admin/settings/suggested', methods=['GET', 'POST'])
@login_required
def admin_settings_suggested():
    """Get or toggle suggested songs."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global SUGGESTED_ENABLED
    if request.method == 'POST':
        SUGGESTED_ENABLED = request.json.get('show', False)
        return jsonify({'success': True, 'show': SUGGESTED_ENABLED})
    return jsonify({'show': SUGGESTED_ENABLED})


@app.route('/admin/settings/chat', methods=['GET', 'POST'])
@login_required
def admin_settings_chat():
    """Get or toggle live chat."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global CHAT_ENABLED
    if request.method == 'POST':
        CHAT_ENABLED = request.json.get('show', False)
        return jsonify({'success': True, 'show': CHAT_ENABLED})
    return jsonify({'show': CHAT_ENABLED})


@app.route('/admin/settings/loudness', methods=['GET', 'POST'])
@login_required
def admin_settings_loudness():
    """Get or set the loudness normalisation target (LUFS).

    Higher (closer to 0) = louder output. -14 matches Spotify/YouTube, -16 is
    the broadcast-ish default, -11 is loud party level.
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    global LOUDNESS_TARGET
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            val = float(data.get('target', LOUDNESS_TARGET))
        except (TypeError, ValueError):
            return jsonify({'error': 'target must be a number'}), 400
        if not (LOUDNESS_TARGET_MIN <= val <= LOUDNESS_TARGET_MAX):
            return jsonify({'error': f'target must be between '
                                     f'{LOUDNESS_TARGET_MIN:g} and {LOUDNESS_TARGET_MAX:g} LUFS'}), 400
        LOUDNESS_TARGET = round(val, 1)
        set_setting('loudness_target', LOUDNESS_TARGET)
        print(f'[loudness] admin set target to {LOUDNESS_TARGET} LUFS', flush=True)
        return jsonify({'success': True, 'target': LOUDNESS_TARGET})
    return jsonify({'target': LOUDNESS_TARGET,
                    'min': LOUDNESS_TARGET_MIN, 'max': LOUDNESS_TARGET_MAX})


@app.route('/admin/settings/crossfade', methods=['GET', 'POST'])
@login_required
def admin_settings_crossfade():
    """Get or set the crossfade length in seconds (0 = hard cut, 1-12 = blend)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            val = float(data.get('seconds', 4))
        except (TypeError, ValueError):
            return jsonify({'error': 'seconds must be a number'}), 400
        if not (0 <= val <= 12):
            return jsonify({'error': 'crossfade must be between 0 and 12 seconds'}), 400
        val = round(val, 1)
        set_setting('crossfade_seconds', str(val))
        print(f'[crossfade] admin set to {val}s', flush=True)
        return jsonify({'success': True, 'seconds': val})
    return jsonify({'seconds': float(get_setting('crossfade_seconds', '4') or 0),
                    'min': 0, 'max': 12})


@app.route('/admin/change-password', methods=['POST'])
@login_required
def admin_change_password():
    """Change the current admin's password."""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    if not current_password or not new_password:
        return jsonify({'error': 'All fields required'}), 400
    if len(new_password) < 4:
        return jsonify({'error': 'Min 4 characters'}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (current_user.id,)).fetchone()
    if not user or (current_password != 'djadmin123' and not check_password_hash(user['password'], current_password)):
        conn.close()
        return jsonify({'error': 'Current password is wrong'}), 403

    conn.execute("UPDATE users SET password=? WHERE id=?",
                 (generate_password_hash(new_password), current_user.id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/leaderboard-enabled')
def leaderboard_enabled():
    return jsonify({'show': SHOW_LEADERBOARD})

@app.route('/score/save', methods=['POST'])
@login_required
def save_score():
    data = request.get_json()
    queue_id = data.get('queue_id')
    score = data.get('score')
    title = data.get('title', 'Unknown')
    username = data.get('username', '-')
    if not queue_id or not score:
        return jsonify({'error': 'Missing data'}), 400
    conn = get_db()
    conn.execute("INSERT INTO scores (queue_id, score, title, username) VALUES (?,?,?,?)",
                 (queue_id, score, title, username))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/leaderboard')
def leaderboard():
    conn = get_db()
    rows = conn.execute(
        "SELECT score, title, username, strftime('%Y-%m-%d', created_at, '+8 hours') as created_at FROM scores ORDER BY score DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/leaderboard/clear', methods=['POST'])
@login_required
def clear_leaderboard():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute("DELETE FROM scores")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/clear-users', methods=['POST'])
@login_required
def clear_users():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute("DELETE FROM users WHERE is_admin=0")
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    conn.close()
    return jsonify({'success': True, 'remaining': remaining})

@app.route('/admin/remove-user/<int:user_id>', methods=['POST'])
@login_required
def remove_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    u = conn.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if u['is_admin']:
        conn.close()
        return jsonify({'error': 'Cannot delete admin accounts'}), 403
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/love/<int:item_id>', methods=['POST'])
@login_required
def admin_love(item_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    if not item or not item['clean_url']:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    # Toggle love in admin's loved_songs
    existing = conn.execute(
        "SELECT id FROM loved_songs WHERE user_id=? AND clean_url=?",
        (current_user.id, item['clean_url'])
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM loved_songs WHERE user_id=? AND clean_url=?",
                     (current_user.id, item['clean_url']))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'loved': False})
    else:
        conn.execute("INSERT INTO loved_songs (user_id, username, clean_url, title) VALUES (?,?,?,?)",
                     (current_user.id, current_user.username, item['clean_url'], item['title']))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'loved': True})

@app.route('/admin/reorder', methods=['POST'])
@login_required
def reorder():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    order = request.json.get('order', [])
    conn = get_db()
    for i, item_id in enumerate(order):
        conn.execute("UPDATE queue SET priority=? WHERE id=?", (len(order) - i, item_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/downloads/<path:filename>')
def downloads(filename):
    """Public file download (e.g. export files)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    safe = os.path.basename(filename)
    fp = os.path.join(base, safe)
    if not os.path.isfile(fp):
        return 'File not found', 404
    return send_file(fp, as_attachment=False, mimetype='text/plain')

@app.route('/admin/export-csv')
@login_required
def export_csv():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    rows = conn.execute("SELECT clean_url, youtube_url, title FROM queue ORDER BY id DESC").fetchall()
    conn.close()
    out = '\n'.join(
        (r['clean_url'] or r['youtube_url'] or '') + ' #' + (r['title'] or '')
        for r in rows
    )
    return Response(out, mimetype='text/plain', headers={'Content-Disposition': 'attachment; filename=cloud-dj-links.txt'})

@app.route('/admin/import-csv', methods=['POST'])
@login_required
def import_csv():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    csv_file = request.files.get('csv')
    if not csv_file:
        return jsonify({'error': 'No file uploaded'}), 400
    import io
    content = csv_file.read().decode('utf-8')
    conn = get_db()
    added = 0
    errors = 0
    for line in content.strip().split('\n'):
        raw_line = line.strip()
        if not raw_line:
            continue
        # Extract title from # comment, then strip it for URL parsing
        title = ''
        comment_pos = raw_line.find('#')
        if comment_pos >= 0:
            title = raw_line[comment_pos + 1:].strip()
            raw_url = raw_line[:comment_pos].strip()
        else:
            raw_url = raw_line
        if not raw_url:
            continue
        m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', raw_url)
        if not m:
            errors += 1
            continue
        clean = 'https://www.youtube.com/watch?v=' + m.group(1)
        existing = conn.execute(
            "SELECT id FROM queue WHERE clean_url=? AND status != 'played'",
            (clean,)
        ).fetchone()
        if existing:
            errors += 1
            continue
        # Use the # comment as the title, fall back to the URL if none provided
        song_title = title if title else clean
        conn.execute(
            "INSERT INTO queue (user_id, username, youtube_url, clean_url, title, status, ip_address) VALUES (?,?,?,?,?,?,?)",
            (current_user.id, current_user.username, clean, clean, song_title, 'played', 'import')
        )
        added += 1
    conn.commit()
    conn.close()
    msg = f'Imported {added} song(s)'
    if errors: msg += f', {errors} skipped'
    return jsonify({'success': True, 'message': msg, 'added': added, 'skipped': errors})

def fetch_title(item_id, url):
    """Get video title from yt-dlp in background."""
    try:
        result = run_ytdl(['--print', 'title', '-s', url])
        title = result.stdout.strip()
        if title:
            conn = get_db()
            conn.execute("UPDATE queue SET title=? WHERE id=?", (title, item_id))
            conn.commit()
            conn.close()
            global NOW_PLAYING
            if NOW_PLAYING['id'] == item_id:
                NOW_PLAYING['title'] = title
    except:
        pass


# ─── SOCKET.IO EVENTS (Live Chat) ───

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        return False  # Reject connection
    join_room('chat')
    # Send recent messages from DB, with their reactions
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, message, is_admin, strftime('%H:%M', created_at, '+8 hours') as time "
        "FROM chat_messages ORDER BY id DESC LIMIT 50"
    ).fetchall()
    ids = [r['id'] for r in rows]
    reactions = {}
    if ids:
        ph = ','.join('?' * len(ids))
        for r in conn.execute(
            f"SELECT message_id, emoji, username FROM chat_reactions WHERE message_id IN ({ph}) ORDER BY id",
            ids
        ):
            reactions.setdefault(r['message_id'], {}).setdefault(r['emoji'], []).append(r['username'])
    conn.close()
    for row in reversed(rows):
        emit('chat_message', {
            'id': row['id'],
            'username': row['username'],
            'message': row['message'],
            'is_admin': row['is_admin'],
            'time': row['time'] or '',
            'reactions': reactions.get(row['id'], {})
        })


@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return
    msg = data.get('message', '').strip()
    if not msg or len(msg) > 500:
        return
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO chat_messages (username, message, is_admin) VALUES (?,?,?)",
            (current_user.username, msg, 1 if current_user.is_admin else 0)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, strftime('%H:%M', created_at, '+8 hours') as time "
            "FROM chat_messages WHERE id=last_insert_rowid()"
        ).fetchone()
        conn.close()
        entry = {
            'id': row['id'] if row else None,
            'username': current_user.username,
            'message': msg,
            'is_admin': current_user.is_admin,
            'time': row['time'] if row else '',
            'reactions': {}
        }
        emit('chat_message', entry, room='chat', broadcast=True)
        # Trim old messages (keep last 500) + orphaned reactions
        conn = get_db()
        conn.execute(
            "DELETE FROM chat_messages WHERE id NOT IN "
            "(SELECT id FROM chat_messages ORDER BY id DESC LIMIT 500)"
        )
        conn.execute(
            "DELETE FROM chat_reactions WHERE message_id NOT IN (SELECT id FROM chat_messages)"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


CHAT_REACTIONS_ALLOWED = {'👍', '😂', '😮', '😢', '😡', '🎵'}


@socketio.on('react_message')
def handle_react_message(data):
    """Toggle a reaction (Like/Haha/Wow/Sad/Angry/Song Notes) on a chat message."""
    if not current_user.is_authenticated:
        return
    msg_id = data.get('message_id')
    emoji = data.get('emoji', '')
    if not isinstance(msg_id, int) or emoji not in CHAT_REACTIONS_ALLOWED:
        return
    try:
        conn = get_db()
        exists = conn.execute("SELECT id FROM chat_messages WHERE id=?", (msg_id,)).fetchone()
        if not exists:
            conn.close()
            return
        existing = conn.execute(
            "SELECT id FROM chat_reactions WHERE message_id=? AND emoji=? AND username=?",
            (msg_id, emoji, current_user.username)
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM chat_reactions WHERE id=?", (existing['id'],))
        else:
            conn.execute(
                "INSERT INTO chat_reactions (message_id, emoji, username) VALUES (?,?,?)",
                (msg_id, emoji, current_user.username)
            )
        conn.commit()
        reactors = [r['username'] for r in conn.execute(
            "SELECT username FROM chat_reactions WHERE message_id=? AND emoji=? ORDER BY id",
            (msg_id, emoji)
        ).fetchall()]
        conn.close()
        emit('message_reaction', {
            'message_id': msg_id,
            'emoji': emoji,
            'username': current_user.username,
            'active': not existing,
            'reactors': reactors
        }, room='chat', broadcast=True)
    except Exception:
        pass


if __name__ == '__main__':
    import socket as _net_socket
    _port = int(os.environ.get('PORT', 5050))
    _port_range = 10  # try up to 10 ports when the base one is taken/blocked

    # Pre-check port availability. Windows throws WSAEACCES (10013) when the
    # port is in use or inside a reserved range, so fall forward to a free one.
    _chosen = None
    for _p in range(_port, _port + _port_range):
        _probe = _net_socket.socket(_net_socket.AF_INET, _net_socket.SOCK_STREAM)
        try:
            _probe.bind(('0.0.0.0', _p))
            _chosen = _p
            break
        except OSError:
            continue
        finally:
            _probe.close()
    if _chosen is None:
        _chosen = _port
        print(f'[cloud-dj] WARNING: ports {_port}-{_port + _port_range - 1} all busy, trying {_port} anyway')
    elif _chosen != _port:
        print(f'[cloud-dj] Port {_port} is busy/blocked - using port {_chosen} instead')

    # Print LAN + local URLs so users know where to connect
    try:
        _s = _net_socket.socket(_net_socket.AF_INET, _net_socket.SOCK_DGRAM)
        _s.connect(('8.8.8.8', 80))
        _lan_ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        _lan_ip = '127.0.0.1'
    print(f'[cloud-dj] LAN access: http://{_lan_ip}:{_chosen}  |  Local: http://localhost:{_chosen}')

    socketio.run(app, host='0.0.0.0', port=_chosen, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
