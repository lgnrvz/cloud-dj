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

Same commands as Linux. No extra setup — the app uses the built-in threading
async mode, so eventlet/gevent are not needed.

### Windows (recommended: one-file .exe)

Download `cloud-dj.exe` from the [Releases](https://github.com/lgnrvz/cloud-dj/releases)
page, double-click it, and open `http://localhost:5050`. The exe bundles
Python, all dependencies, yt-dlp, and ffmpeg — no install needed.

Change the port with: `PORT=9090 cloud-dj.exe` (or set the `PORT` env var).

### Windows (installer script)

Run the full automated installer (installs Python, Git, ffmpeg, firewall rule,
auto-start):

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Or manually, same commands as Linux. The app auto-selects a compatible async
mode on Windows, so no config edits are needed.

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
