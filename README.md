# Cloud-DJ

LAN music queue with YouTube playback, live chat, and admin controls.

## Features

- **YouTube Queue** — Add songs via URL, auto-plays next
- **Live Chat** — Real-time chat with Socket.IO, links auto-linkify
- **Suggested Songs** — Random picks from history, refreshes every 60s
- **Queue Voting** — Heart songs you like
- **Admin Controls** — Skip, remove, reorder, manage history
- **Scoring / Leaderboard** — Videoke-style scoring (toggleable)
- **Drag & Drop** — Reorder the queue (admin only)

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5050` in your browser.

### Mac (Apple Silicon / Intel)

Same steps, but if `eventlet` fails to install (known issue on Mac), use gevent instead:

```bash
pip install -r requirements.txt
pip uninstall eventlet -y
pip install gevent gevent-websocket
```

Then in `app.py`, change async mode:
```python
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
```

Or use threading mode (no extra deps, works everywhere):
```python
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
```

### Windows

```bash
pip install -r requirements.txt
python app.py
```

> **Note:** On Windows, eventlet may also fail — use the same gevent fallback above.

## Install on a Server

```bash
# Clone
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj

# Install
pip install -r requirements.txt

# Run (or set up as a service)
python app.py
```

## Admin Panel

Go to `/admin` after logging in as admin.

| Setting | Default | Description |
|---------|---------|-------------|
| Scoring | Off | Videoke scoring popup |
| Leaderboard | Off | Show leaderboard sidebar |
| Suggested Songs | On | Random song suggestions from history |
| Live Chat | On | Real-time chat for all users |

### Admin credentials

```
Username: admin
Password: djadmin123
```

Change the password in the admin panel after first login.

## Layout

```
┌──────────┬────────────────┬──────────┐
│   Left   │    Middle      │   Right  │
│   (20%)  │    (60%)       │   (20%)  │
├──────────┼────────────────┼──────────┤
│ Search   │ Now Playing    │ Quick Add│
│ Suggested│ Video Player   │ Leaderbd │
│ Live Chat│ Status         │ Loved    │
│          │ Queue          │          │
└──────────┴────────────────┴──────────┘
```

## Tech Stack

- **Backend:** Flask + Flask-SocketIO + Eventlet
- **Frontend:** jQuery, vanilla JS, Socket.IO client
- **Video:** yt-dlp (direct stream URLs)
- **Database:** SQLite with FTS5 search

## Ports & URLs

- **Web UI:** `http://<server>:5050`
- **Login:** `/login`
- **Admin:** `/admin`
