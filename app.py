from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, threading, subprocess, re, signal, random, time
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
NOW_PLAYING = {'id': None, 'url': None, 'title': 'Nothing playing', 'username': '-', 'stream_url': None}

NODE_PATH = '/home/raspberrypi/.local/bin/node'
YTDLP = '/usr/local/bin/yt-dlp'

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
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        conn.execute("INSERT INTO users (name, username, password, is_admin) VALUES (?, ?, ?, ?)",
                     ('Admin', 'admin', generate_password_hash('djadmin123'), 1))
    conn.commit()
    conn.close()

init_db()

def clean_yt_url(url):
    match = re.search(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/))([\w-]+)', url)
    if match:
        return f'https://www.youtube.com/watch?v={match.group(2)}'
    return None

def run_ytdl(args, timeout=20):
    cmd = [YTDLP, '--js-runtimes', f'node:{NODE_PATH}'] + args
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

# ─── HELPERS ───

def get_next_pending():
    """Return the next pending queue item, or None."""
    conn = get_db()
    item = conn.execute(
        "SELECT * FROM queue WHERE status='pending' ORDER BY priority DESC, id ASC LIMIT 1"
    ).fetchone()
    conn.close()
    return item

def set_now_playing(item):
    """Update NOW_PLAYING from a queue item (dict/Row) or None (-> Auto-DJ)."""
    global NOW_PLAYING
    if item is None:
        NOW_PLAYING = {
            'id': -1,
            'url': None,
            'title': 'Auto-DJ',
            'username': 'Cloud DJ',
            'stream_url': '/stream/auto-dj'
        }
    else:
        NOW_PLAYING = {
            'id': item['id'],
            'url': item['clean_url'] or item['youtube_url'],
            'title': item['title'],
            'username': item['username'],
            'stream_url': f"/stream/{item['id']}"
        }

# ─── AUTO-DJ ───

AUTO_DJ_SEARCHES = [
    "ytsearch:best upbeat party mix 2026",
    "ytsearch:feel good music mix 2026",
    "ytsearch:upbeat happy music mix",
    "ytsearch:dance pop mix 2026",
    "ytsearch:energetic workout music mix",
    "ytsearch:chill electronic mix 2026",
    "ytsearch:indie pop hits mix",
]

# ─── ROUTES ───

@app.route('/')
def index():
    return redirect(url_for('queue'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name'].strip()
        username = request.form['username'].strip()
        password = request.form['password']
        if not name or not username or not password:
            flash('All fields required!', 'danger')
            return render_template('signup.html')
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (name, username, password) VALUES (?,?,?)",
                         (name, username, generate_password_hash(password)))
            conn.commit()
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
        if u and check_password_hash(u['password'], password):
            login_user(User(u), remember=True)
            session.permanent = True
            return redirect(url_for('queue'))
        flash('Invalid credentials!', 'danger')
    return render_template('login.html')

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
        "SELECT * FROM queue WHERE status != 'played' ORDER BY CASE WHEN status='playing' THEN 0 ELSE 1 END, priority DESC, id ASC"
    ).fetchall()
    played = conn.execute(
        "SELECT * FROM queue WHERE status='played' ORDER BY id DESC LIMIT 10"
    ).fetchall()
    loved = conn.execute(
        "SELECT * FROM loved_songs WHERE user_id=? ORDER BY loved_at DESC LIMIT 50",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template('queue.html', items=items, played=played, loved=loved, now=dict(NOW_PLAYING))

@app.route('/now-playing')
def now_playing():
    np = dict(NOW_PLAYING)
    conn = get_db()
    items = conn.execute(
        "SELECT COUNT(*) as c FROM queue WHERE status='pending'"
    ).fetchone()
    conn.close()
    np['queue_count'] = items['c'] if items else 0
    return jsonify(np)

@app.route('/add', methods=['POST'])
@login_required
def add():
    raw_url = request.form['url'].strip()
    clean_url = clean_yt_url(raw_url)
    if not clean_url:
        flash('Invalid YouTube link!', 'danger')
        return redirect(url_for('queue'))

    # Duration check
    try:
        result = run_ytdl(['--print', 'duration', '-s', clean_url])
        dur = result.stdout.strip()
        if dur and dur.isdigit():
            d = int(dur)
            if d > 600:
                flash(f'Too long! Max 10 min (this is {d//60}m{d%60}s).', 'danger')
                return redirect(url_for('queue'))
    except subprocess.TimeoutExpired:
        flash('Could not verify duration - try again.', 'danger')
        return redirect(url_for('queue'))
    except:
        pass

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM queue WHERE user_id=? AND clean_url=? AND loved=1",
        (current_user.id, clean_url)
    ).fetchone()
    if existing:
        conn.close()
        flash('You already added this song!', 'warn')
        return redirect(url_for('queue'))

    ip = request.remote_addr or 'unknown'
    conn.execute(
        "INSERT INTO queue (user_id, username, youtube_url, clean_url, ip_address) VALUES (?,?,?,?,?)",
        (current_user.id, current_user.username, raw_url, clean_url, ip)
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    # Fetch title in background
    threading.Thread(target=fetch_title, args=(item_id, clean_url), daemon=True).start()

    # If Auto-DJ is playing, kick the browser to advance
    if NOW_PLAYING.get('id') == -1:
        auto_advance()

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

@app.route('/love/<int:item_id>', methods=['POST'])
@login_required
def love_toggle(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if item['user_id'] != current_user.id:
        conn.close()
        return jsonify({'error': 'Not your song'}), 403
    new_val = 0 if item['loved'] else 1
    conn.execute("UPDATE queue SET loved=? WHERE id=?", (new_val, item_id))
    if new_val:
        existing = conn.execute(
            "SELECT id FROM loved_songs WHERE user_id=? AND clean_url=?",
            (current_user.id, item['clean_url'])
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO loved_songs (user_id, username, clean_url, title) VALUES (?,?,?,?)",
                (current_user.id, current_user.username, item['clean_url'], item['title'])
            )
    else:
        conn.execute(
            "DELETE FROM loved_songs WHERE user_id=? AND clean_url=?",
            (current_user.id, item['clean_url'])
        )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'loved': new_val})

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

    if NOW_PLAYING.get('id') == -1:
        auto_advance()

    return jsonify({'success': True, 'title': song['title']})

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
        proc = subprocess.Popen(
            [YTDLP, '--js-runtimes', f'node:{NODE_PATH}',
             '-f', 'bestaudio', '-q', '-o', '-', url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        try:
            while True:
                data = proc.stdout.read(16384)
                if not data:
                    break
                yield data
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except:
                pass
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

@app.route('/stream/auto-dj')
def stream_auto_dj():
    """Stream a random upbeat mix from YouTube."""
    search = random.choice(AUTO_DJ_SEARCHES)

    def generate():
        proc = subprocess.Popen(
            [YTDLP, '--js-runtimes', f'node:{NODE_PATH}',
             '-f', 'bestaudio', '-q', '-o', '-', search],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        try:
            while True:
                data = proc.stdout.read(16384)
                if not data:
                    break
                yield data
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except:
                pass
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

# ─── PLAYER ADVANCEMENT ───

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

    # Mark current as played if it's a real queue item
    if current_id and current_id > 0:
        conn = get_db()
        conn.execute("UPDATE queue SET status='played' WHERE id=?", (current_id,))
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

    return jsonify(dict(NOW_PLAYING))

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
        # Put it back as pending (it'll re-queue at the end)
        conn = get_db()
        conn.execute("UPDATE queue SET status='pending' WHERE id=?", (current_id,))
        conn.commit()
        conn.close()

    next_item = get_next_pending()
    set_now_playing(next_item)
    if next_item:
        conn = get_db()
        conn.execute("UPDATE queue SET status='playing' WHERE id=?", (next_item['id'],))
        conn.commit()
        conn.close()

    return jsonify(dict(NOW_PLAYING))

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
    history = conn.execute(
        "SELECT * FROM queue WHERE status='played' ORDER BY id DESC LIMIT 30"
    ).fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', items=items, history=history, users=users, now=dict(NOW_PLAYING))

@app.route('/admin/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_item(item_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
