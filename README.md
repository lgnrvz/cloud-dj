# Cloud-DJ

LAN music queue with YouTube playback, live chat, and admin controls.

## Install

### Linux / Raspberry Pi

```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
pip install -r requirements.txt
python app.py
```

### Mac

```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
pip install -r requirements.txt
python app.py
```

If eventlet fails to install, use gevent instead:

```bash
pip uninstall eventlet -y
pip install gevent gevent-websocket
```

Then in `app.py` change line 56:
```python
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
```

### Windows

```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
pip install -r requirements.txt
python app.py
```

If eventlet fails, follow the same gevent fallback as Mac above.

## Login

Open `http://localhost:5050` and sign up, or use the admin account:

```
Username: admin
Password: djadmin123
```

## Features

- YouTube queue — paste a link, it plays
- Live chat — real-time with clickable links
- Suggested songs — random picks from history
- Queue voting — heart songs you like
- Videoke scoring — toggleable in admin panel
- Admin controls — skip, remove, reorder, manage users

## Tech

Flask, Socket.IO, SQLite, yt-dlp

---

[GitHub](https://github.com/lgnrvz/cloud-dj)
