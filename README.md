# Cloud DJ

A self-hosted videoke-style music queue system where **music plays in the browser**, not on the server. Anyone can add songs via YouTube links, but playback happens on the admin's machine through their web browser with video.

Perfect for parties, events, or shared spaces — run it on a Raspberry Pi and let guests queue songs from their phones while the admin's laptop/TV plays the video and audio.

## How It Works

```
Guest ──paste YouTube link──> Web App ──queue──> yt-dlp stream ──> Admin's Browser (video + audio)
```

- **Anyone** can paste YouTube links on the website → songs go to a queue
- **Admin's browser** is the player — video + audio streams directly to the browser
- **Auto-DJ** shuffles through previously played songs when the queue is empty
- **Videoke Scoring** — confetti, applause, and a score (70-100) when a song finishes (admin toggle)
- **Leaderboard** — top 10 scores ranked #1, #2, #3 with song title and who requested it
- No audio plays through the Raspberry Pi's speakers

## Features

### For Everyone
- **Paste to add** — Paste a YouTube link in the input box to queue instantly
- **♥ Love songs** — Save favorites to a personal list
- **Auto-DJ** — Plays random songs from history when the queue runs out
- **10-min limit** — Songs over 10 minutes are blocked
- **Duplicate prevention** — Same song can't be added twice to the queue
- **Real-time queue updates** — See new songs appear as others add them
- **Sign up** — Create your own account to track loved songs

### For Admins
- **Browser player** — Video + audio plays in the admin's browser tab
- **Skip** — Skip current track, automatically plays the next in queue
- **Queue list** — See all pending songs, who added them
- **History with request counters** — 15 per page with prev/next navigation, love buttons
- **Clear / delete history** — Clear all or remove individual entries
- **Manage loved songs** — Remove songs from your loved list
- **Love from history** — ♥ any played song to add to loved songs
- **User list** — See all registered users

### Videoke Scoring (Admin Toggle)
- **Confetti bomb** — 500 particles explode from the bottom, 300 rain from the top
- **Audience applause** — Real clapping sound effect (4.5s)
- **Score popup** — Big animated score (70-100) with Filipino comments like "Sobrang galing!"
- **Leaderboard** — Top 10 scores saved and displayed (admin toggle)
- Toggle on/off from Admin → Settings

### Auto-DJ
When the queue runs out, Auto-DJ automatically shuffles through previously played songs. When someone adds a new song, it transitions into the queue immediately.

## Requirements

- **Raspberry Pi** (any model — Pi 3 or 4 recommended)
- **Python 3.8+**
- **Node.js** (required by yt-dlp for YouTube extraction)
- **yt-dlp** (latest from GitHub)

## Installation

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm curl
```

### 2. Install yt-dlp

```bash
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp
```

### 3. Clone the repo and set up

```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
python3 -m venv venv
source venv/bin/activate
pip install flask flask-login
```

### 4. Configure Node.js path (if needed)

yt-dlp needs a JavaScript runtime. Check your Node.js location:

```bash
which node
# Usually /usr/bin/node or /usr/local/bin/node
```

If your Node.js is in a different location, edit the `NODE_PATH` variable in `app.py`:

```python
NODE_PATH = '/usr/bin/node'  # Change to match your system
```

### 5. Start the server

```bash
cd cloud-dj
source venv/bin/activate
python app.py
```

The server runs on **port 5050**.

### 6. Access the web app

| Network | URL |
|---------|-----|
| Same machine | http://localhost:5050 |
| Local network | http://<raspberry-pi-ip>:5050 |

### Default Admin Login

| User | Password |
|------|----------|
| `admin` | `djadmin123` |

**Change the password after first login!**

## Run as a Service (systemd)

To keep Cloud DJ running after you close the terminal:

```bash
sudo nano /etc/systemd/system/cloud-dj.service
```

Paste:

```
[Unit]
Description=Cloud DJ
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/cloud-dj
ExecStart=/home/pi/cloud-dj/venv/bin/python /home/pi/cloud-dj/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl enable cloud-dj
sudo systemctl start cloud-dj
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | — | Redirects to queue |
| `/queue` | GET | Login | Main queue page with player |
| `/admin` | GET | Admin | Admin panel (history, users, settings) |
| `/login` | GET/POST | — | User login |
| `/signup` | GET/POST | — | User registration |
| `/logout` | GET | Login | Logout |
| `/add` | POST | Login | Add song to queue |
| `/now-playing` | GET | — | Currently playing song (JSON) |
| `/advance` | POST | Login | Advance to next track |
| `/skip` | GET | Admin | Skip current track |
| `/direct-video` | GET | — | Get direct video stream URL (format 18) |
| `/love/<id>` | POST | Login | Toggle love on queue item |
| `/loved/add/<id>` | POST | Login | Add loved song to queue |
| `/loved/remove/<id>` | POST | Login | Delete loved song |
| `/scoring-enabled` | GET | — | Check if videoke scoring is on |
| `/score/save` | POST | Login | Save a videoke score |
| `/leaderboard` | GET | — | Top 10 scores (JSON) |
| `/leaderboard/clear` | POST | Admin | Clear all scores |
| `/leaderboard-enabled` | GET | — | Check if leaderboard is visible |
| `/admin/history` | GET | Admin | Paginated history (JSON) |
| `/admin/love/<id>` | POST | Admin | Love any history item |
| `/admin/settings` | GET/POST | Admin | Toggle videoke scoring |
| `/admin/settings/leaderboard` | GET/POST | Admin | Toggle leaderboard visibility |
| `/admin/remove/<id>` | POST | Admin | Remove queue item |
| `/admin/clear-history` | POST | Admin | Delete all played history |

## Project Structure

```
cloud-dj/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── static/
│   └── applause.wav       # Audience clapping sound effect
├── templates/
│   ├── base.html          # Base layout
│   ├── queue.html         # Main queue page with browser player
│   ├── admin.html         # Admin panel (history, users, settings)
│   ├── login.html         # Login page
│   └── signup.html        # Registration page
├── .gitignore
└── README.md
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| yt-dlp fails: "JS runtime not found" | Install Node.js and set `NODE_PATH` in app.py |
| Video won't play in browser | Check `/direct-video` endpoint — yt-dlp may need updating |
| "Click play" message | Click the video player once — subsequent tracks auto-play |
| Queue items stuck as "playing" | Server auto-cleans stale entries on next track advance |
| Port 5050 already in use | Change port in `app.py`: `app.run(host='0.0.0.0', port=5050)` |

## Updating

```bash
cd cloud-dj
git pull
source venv/bin/activate
pip install -r requirements.txt
# Restart the server
```

## License

MIT
