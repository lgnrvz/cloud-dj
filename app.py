from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context, session
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
NOW_PLAYING = {'id': None, 'url': None, 'title': 'Nothing playing', 'username': '-', 'is_auto_dj': False}
SCORING_ENABLED = False  # Videoke scoring toggle
SHOW_LEADERBOARD = False  # Leaderboard visibility toggle

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
    conn.execute("""CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        title TEXT DEFAULT 'Unknown',
        username TEXT DEFAULT '-',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        conn.execute("INSERT INTO users (name, username, password, is_admin) VALUES (?, ?, ?, ?)",
                     ('Admin', 'admin', generate_password_hash('djadmin123'), 1))
    conn.commit()
    conn.close()

init_db()

def clean_yt_url(url):
    match = re.search(r'(https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/))([\w-]+)', url)
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
    """Return the next pending queue item, or None.
    Also cleans up stale 'playing' items (stuck from crashes)."""
    conn = get_db()
    # Reset any stale 'playing' items to 'played' (they never advanced)
    conn.execute("UPDATE queue SET status='played' WHERE status='playing' AND id != ?",
                 (NOW_PLAYING.get('id', -1),))
    conn.commit()
    item = conn.execute(
        "SELECT * FROM queue WHERE status='pending' ORDER BY priority DESC, id ASC LIMIT 1"
    ).fetchone()
    conn.close()
    return item

def set_now_playing(item):
    """Update NOW_PLAYING from a queue item (dict/Row) or None (-> Auto-DJ from history)."""
    global NOW_PLAYING
    if item is None:
        # Auto-DJ: shuffle a random previously played song
        conn = get_db()
        played = conn.execute(
            "SELECT * FROM queue WHERE status='played' ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        conn.close()
        if played:
            NOW_PLAYING = {
                'id': -1,
                'url': played['clean_url'] or played['youtube_url'],
                'title': 'Auto-DJ: ' + (played['title'] or 'Unknown'),
                'username': 'Cloud DJ',
                'is_auto_dj': True
            }
        else:
            NOW_PLAYING = {
                'id': None, 'url': None, 'title': 'Nothing playing',
                'username': '-', 'is_auto_dj': False
            }
    else:
        NOW_PLAYING = {
            'id': item['id'],
            'url': item['clean_url'] or item['youtube_url'],
            'title': item['title'],
            'username': item['username'],
            'is_auto_dj': False
        }

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
    # Get set of loved URLs for the current user (for heart state on queue items)
    loved_urls = set(r['clean_url'] for r in loved if r['clean_url'])
    conn.close()
    # Auto-start: if nothing is playing but there are pending items, advance
    if NOW_PLAYING.get('id') is None:
        _auto_start()
    return render_template('queue.html', items=items, played=played, loved=loved, loved_urls=loved_urls, now=_enrich_now(dict(NOW_PLAYING)))

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
    # Add queue count if not present
    if 'queue_count' not in np:
        conn = get_db()
        c = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status='pending'").fetchone()
        np['queue_count'] = c['cnt'] if c else 0
        conn.close()
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
        result = run_ytdl(['--print', 'duration', '-s', clean_url])
        dur = result.stdout.strip()
        if dur and dur.isdigit():
            d = int(dur)
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
    except:
        pass

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

    if NOW_PLAYING.get('id') == -1:
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

@app.route('/direct-video')
def direct_video():
    """Return a direct Google video URL for browser HTML5 <video> playback."""
    url = request.args.get('url', '')
    m = re.search(r'(?:v=|/)([\w-]{11})(?:\?|&|$)', url)
    if not m:
        return jsonify({'error': 'Invalid URL'}), 400
    try:
        result = subprocess.run(
            [YTDLP, '--js-runtimes', f'node:{NODE_PATH}',
             '-g', '-f', '18', url],
            capture_output=True, text=True, timeout=15
        )
        video_url = result.stdout.strip().split('\n')[0]
        if video_url:
            return jsonify({'video_url': video_url, 'video_id': m.group(1)})
    except:
        pass
    return jsonify({'error': 'Failed to get video URL'}), 500

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
                   'is_admin': bool(r['is_admin']), 'created_at': r['created_at']} for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

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
    rows = conn.execute("""
        SELECT q.*,
            (SELECT COUNT(*) FROM queue WHERE clean_url = q.clean_url) as request_count
        FROM queue q
        WHERE q.status='played'
        ORDER BY q.id DESC LIMIT ? OFFSET ?
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
        "SELECT score, title, username, created_at FROM scores ORDER BY score DESC LIMIT 10"
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
