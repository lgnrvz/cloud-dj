# Cloud-DJ

LAN music queue with YouTube playback, live chat, and admin controls.

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5050`. Log in as `admin` / `djadmin123`.

## Features

- YouTube queue — paste a link, it plays
- Live chat — real-time, links auto-linkify
- Suggested songs — random picks from history
- Queue voting — heart songs you like
- Videoke scoring — toggleable
- Admin panel — skip, remove, reorder, manage users

## Install

Works on Linux, Mac, and Windows. If `eventlet` fails to install (Mac/Windows), swap it:

```bash
pip uninstall eventlet -y
pip install gevent gevent-websocket
```

Then change async mode in `app.py` to `'gevent'` or `'threading'`.

## Tech

Flask, Socket.IO, SQLite, yt-dlp. Single-file backend.

---

[GitHub](https://github.com/lgnrvz/cloud-dj)
