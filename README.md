# Cloud-DJ

A self-hosted LAN music queue app. Anyone on the network can paste a YouTube link to add a song, see what's playing, vote with hearts, and chat in real-time. Designed for parties, videoke nights, and office jams.

## Features

- YouTube queue — paste a link, it plays. Supports `music.youtube.com` links too
- Live chat — real-time Socket.IO chat with clickable link detection
- Suggested songs — random picks from history, refreshes every 60s
- Queue voting — heart your favorite songs
- Videoke scoring — toggleable scoring with popup animations
- Queue management — drag to reorder, remove, or skip (admin)
- Admin panel — manage users, history, settings, and import/export songs
- Search history — FTS5-powered search across played songs

## Install

### Linux / Raspberry Pi

```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
pip install -r requirements.txt
python app.py
```

### Mac

Same commands as Linux. If eventlet fails:

```bash
pip uninstall eventlet -y
pip install gevent gevent-websocket
```

Then in `app.py` line 56, change `async_mode='eventlet'` to `async_mode='gevent'`.

### Windows

Same commands as Linux. Same eventlet fallback as Mac if needed.

## Login

Open `http://localhost:5050` and sign up, or use the admin account:

```
Username: admin
Password: djadmin123
```

## Tech

Flask, Socket.IO, SQLite (FTS5), yt-dlp.

---

Support the dev: [Patreon](https://www.patreon.com/c/NRVZ)
