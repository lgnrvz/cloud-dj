# Cloud DJ

A self-hosted music queue system where **music plays in the browser**, not on the server. Anyone can add songs, but playback happens on the admin's machine through their web browser.

## How It Works

```
User ──add YouTube link──> Web App ──queue──> yt-dlp stream ──> Admin's Browser
```

- **Users** paste YouTube links on the website → songs go to a queue
- **Admin's browser** is the player — audio streams from the server via yt-dlp directly to the browser's `<audio>` element
- **Auto-DJ** plays upbeat mixes when the queue is empty (streamed to browser)
- No audio plays through the server's speakers — perfect for headless setups

## Architecture

Unlike traditional setups where the server plays audio locally (yt-dlp → ffmpeg → speaker), Cloud DJ:

1. **Server** manages the queue, user auth, and streams audio on demand
2. **Admin's browser** fetches audio via `/stream/<id>` and plays it natively
3. When a track ends, the browser calls `/advance` to move to the next song
4. Auto-DJ streams from `/stream/auto-dj` when the queue is empty

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Redirects to queue |
| `/queue` | GET | Main queue page with browser player |
| `/admin` | GET | Admin panel (drag reorder, remove) |
| `/login` | GET/POST | User login |
| `/signup` | GET/POST | User registration |
| `/logout` | GET | Logout |
| `/add` | POST | Add song to queue |
| `/love/<id>` | POST | Toggle love on queue item |
| `/loved/add/<id>` | POST | Add loved song to queue |
| `/now-playing` | GET | Currently playing song (JSON) |
| `/advance` | POST | Advance to next track (browser calls) |
| `/skip` | GET | Skip current track |
| `/stream/<id>` | GET | Audio stream for a queue item |
| `/stream/auto-dj` | GET | Auto-DJ audio stream |
| `/admin/remove/<id>` | POST | Remove queue item (admin) |
| `/admin/reorder` | POST | Save queue order (admin) |

## Quick Start

```bash
# Install dependencies
sudo apt install -y python3 python3-pip python3-venv
pip3 install flask flask-login

# Install yt-dlp (latest)
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# Clone and run
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
python3 app.py
```

Open `http://<your-ip>:5050` in a browser.

### Default Admin Login

| User | Password |
|------|----------|
| `admin` | `djadmin123` |

## Features

### For Everyone
- **Paste to add** — Ctrl+V any YouTube link anywhere on the page to queue a song
- **♥ Love songs** — Save favorites to a personal list for easy re-queuing
- **Now Playing** — See what's currently playing with live updates
- **10-min limit** — Songs over 10 minutes are blocked

### For Admins
- **Browser-based player** — Audio plays through your browser, not the server
- **Skip** — Skip to the next track
- **Drag to reorder** — Rearrange the queue by dragging items
- **Remove** — Delete unwanted songs from the queue
- **User list** — See all registered users
- **Queue history** — View recently played songs

### Auto-DJ
When the queue runs out, Auto-DJ automatically plays upbeat party mixes streamed to the admin's browser. When someone adds a new song, the browser transitions to the queue.

## Requirements

- **Python 3.8+**
- **Flask + Flask-Login**
- **yt-dlp** (latest from GitHub recommended)
- **Node.js** — Required by yt-dlp for YouTube extraction (configure path in `app.py`)

## Project Structure

```
cloud-dj/
├── app.py                 # Flask application
├── templates/
│   ├── base.html          # Base layout
│   ├── queue.html         # Main queue page with browser player
│   ├── admin.html         # Admin panel
│   ├── login.html         # Login page
│   └── signup.html        # Registration page
├── .gitignore
└── README.md
```

## License

MIT
