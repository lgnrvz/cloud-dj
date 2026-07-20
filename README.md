# ☁️ Cloud-DJ

> A self-hosted music queue system. Guests paste YouTube links from their phones, the admin's browser plays the audio/video. Perfect for parties, offices, bars, and shared spaces.

[![Python](https://img.shields.io/badge/python-3.8%2B-1db954?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/flask-3.x-000?logo=flask)](https://flask.palletsprojects.com)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/license-CC%20BY--NC%204.0-ffd700.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)](#installation)

---

## ✨ Features

### 🎵 Queue Management
- **Paste-to-queue** — paste any YouTube link, instantly added to the shared queue
- **Real-time sync** — new songs appear on everyone's screen as they're added
- **♥ Loved songs** — save favorites to your personal library, re-queue with one tap
- **Duplicate prevention** — same URL can't be queued twice
- **10-minute cap** — videos over 10 min are blocked (with proper verification)
- **Queue Limit** — prevents one person from flooding (configurable 1–16, auto-resets after 5 min)
- **Admin is unlimited** — queue limit doesn't apply to admin accounts
- **Signup rate limiting** — blocks rapid account creation from the same IP

### ▶️ Auto-DJ
- **Auto-fill** — when the queue is empty, shuffles through previously played songs
- **Skip** — click Skip to jump to a new random track (no repeats of the last 8)
- **Seamless transition** — when someone adds a new song, Auto-DJ hands off to the real queue
- **No history yet?** Skip button is hidden until there's something to shuffle

### 🎤 Scoring & Leaderboard
- **Videoke mode** — confetti explosion + applause + score popup (70–100) when a song finishes
- **Leaderboard** — top 10 scores tracked with song + requester
- **Toggle anytime** — turn scoring on/off mid-party from Admin → Settings

### 🛡️ Admin Controls
- **Browser player** — video + audio plays in your browser tab (no external player needed)
- **Skip / reorder / remove** — full queue control
- **User management** — view all users, remove troublemakers
- **Clear history** — wipe played songs (scores are preserved)
- **Anti-abuse settings** — configure queue limit from the admin panel
- **Change password** — update admin password from Settings (requires current password)

---

## 🚀 Quick Start

### Prerequisites

| Tool | Purpose |
|------|---------|
| **Python 3.8+** | Flask + app runtime |
| **Node.js** | Required by yt-dlp for YouTube extraction |
| **ffmpeg** | yt-dlp post-processing (recommended) |
| **yt-dlp** | Downloads YouTube audio/video streams |
| **Git** | Cloning the repository |

### Minimum Specs

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 1 core @ 1 GHz | 2 cores @ 1.2 GHz |
| **RAM** | 256 MB | 512 MB+ |
| **Storage** | 200 MB | 500 MB |
| **Network** | Any Wi-Fi / Ethernet | Wired Ethernet preferred |
| **OS** | Linux (any distro) or Windows 10+ | — |

**Raspberry Pi compatibility:** Pi 3B, 3B+, 4, 400, 5, Zero 2 W — all confirmed working.  
The server doesn't transcode or stream media — the admin's browser streams directly from YouTube's CDN, so the Pi only handles lightweight web requests and yt-dlp metadata lookups.

---

### 🐧 Linux (any distro)

**One-liner:**
```bash
curl -sSL https://raw.githubusercontent.com/lgnrvz/cloud-dj/main/install.sh | bash
```

**Or step by step:**
```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
./install.sh
```

**Custom port:**
```bash
PORT=9090 ./install.sh
```

The installer:
- Detects your distro and installs system dependencies via `apt`/`dnf`/`pacman`
- Creates a Python virtual environment with all dependencies
- Registers a **systemd service** that auto-starts on boot
- Opens port 5050 in your firewall (`ufw`/`firewalld`)
- Starts the server and prints your LAN URL

---

### Windows (10 / 11)

**One-liner (PowerShell as Administrator):**
```powershell
powershell -ExecutionPolicy Bypass -c "iwr -useb https://raw.githubusercontent.com/lgnrvz/cloud-dj/main/install.ps1 | iex"
```

**Or step by step:**
```powershell
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Or the lazy way:** Right-click `install.ps1` → **Run with PowerShell**.

**Custom port:**
```powershell
$env:PORT=9090; powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer:
- Checks for Python, Node.js, ffmpeg — installs via **winget** if missing
- Creates a Python virtual environment with all dependencies
- Opens port 5050 in **Windows Firewall**
- Registers a **Scheduled Task** that auto-starts on boot
- Adds a **Cloud-DJ shortcut to your desktop** 🖥️
- Starts the server and prints your LAN URL

---

### 🔐 After Installation

**Default admin credentials:**
```
Username: admin
Password: djadmin123
```

**Access URLs:**

| Location | URL |
|----------|-----|
| Same machine | `http://localhost:5050` |
| Local network | `http://<your-pc-ip>:5050` |

> ⚠️ **Change the admin password after first login** via the Admin panel's User management.

---

## 📖 Usage

### Adding a Song
1. Open the web app on any device on the same network
2. Sign up or log in
3. Paste a YouTube link and hit Enter
4. The song appears in the queue — when it reaches the front, the admin's browser plays it

### Admin Panel
- Log in as `admin` → click **Admin** in the top bar
- **Queue:** reorder (drag), remove, love songs
- **History:** browse played songs, re-love, view request counts
- **Users:** see all registered users, remove unwanted accounts
- **Settings:**
  - Videoke Scoring — toggle on/off
  - Show Leaderboard — toggle visibility
  - Queue Limit — set max consecutive songs per user (1–16)

### Auto-DJ Controls
- **Skip button** — visible on the queue page for admin. When Auto-DJ is active, click to shuffle to a different random song. When a real queue is playing, skips to the next queued song.

---

## 🔧 Server Management

### Linux (systemd)
```bash
sudo systemctl status cloud-dj    # check status
sudo systemctl stop cloud-dj      # stop server
sudo systemctl start cloud-dj     # start server
sudo systemctl restart cloud-dj   # restart server
sudo journalctl -u cloud-dj -f    # follow logs
```

### Windows
```powershell
.\start-cloud-dj.bat              # start server (or use desktop shortcut)

# View logs
Get-Content "$env:USERPROFILE\cloud-dj\server.log" -Wait
```

---

## 🔄 Updating

### Linux
```bash
cd ~/cloud-dj
git pull
./install.sh
```

### Windows
```powershell
cd $env:USERPROFILE\cloud-dj
git pull
powershell -ExecutionPolicy Bypass -File install.ps1
```

---

## 📁 Project Structure

```
cloud-dj/
├── app.py                    # Flask application
├── install.sh                # Linux installer
├── install.ps1               # Windows installer
├── requirements.txt          # Python dependencies
├── static/
│   └── applause.wav          # Audience clapping sound
├── templates/
│   ├── queue.html            # Main queue page + browser player
│   ├── admin.html            # Admin panel
│   ├── login.html            # Login page
│   ├── signup.html           # Registration page
│   └── base.html             # Base layout
├── .gitignore
└── README.md
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| yt-dlp: "JS runtime not found" | Install Node.js. Linux: `sudo apt install nodejs`. Windows: re-run the installer. |
| Video won't play | Update yt-dlp: `pip install -U yt-dlp`, then restart the server. |
| "Click play" message | Click the video player once — subsequent tracks auto-play. |
| Queue stuck on "playing" | Server auto-cleans stale entries on the next track advance. |
| Port 5050 already in use | Use a custom port: `PORT=9090 ./install.sh` or `$env:PORT=9090`. |
| Can't access from other devices | Check firewall: Linux → `ufw allow 5050`. Windows → check Windows Defender Firewall. |
| Can't reach LAN URL | Ensure both devices are on the **same network** with no guest isolation. |

---

## ⚙️ API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | — | Redirect to queue |
| `/queue` | GET | Login | Main queue page |
| `/admin` | GET | Admin | Admin panel |
| `/login` | GET/POST | — | Authentication |
| `/signup` | GET/POST | — | Account creation (rate-limited) |
| `/logout` | GET | Login | End session |
| `/add` | POST | Login | Add song to queue |
| `/now-playing` | GET | — | Current track info (JSON) |
| `/advance` | POST | Login | Advance to next track |
| `/skip` | GET | Admin | Skip current track |
| `/direct-video` | GET | — | Direct stream URL for player |
| `/love/<id>` | POST | Login | Toggle loved song |
| `/loved/add/<id>` | POST | Login | Queue from loved songs |
| `/loved-songs` | GET | Login | Paginated loved songs (JSON) |
| `/scoring-enabled` | GET | — | Videoke toggle state (JSON) |
| `/score/save` | POST | Login | Save videoke score |
| `/leaderboard` | GET | — | Top 10 scores (JSON) |
| `/admin/history` | GET | Admin | Paginated play history (JSON) |
| `/admin/users` | GET | Admin | Paginated user list (JSON) |
| `/admin/remove/<id>` | POST | Admin | Remove queue item |
| `/admin/clear-history` | POST | Admin | Delete all played songs |
| `/admin/remove-user/<id>` | POST | Admin | Delete a user |
| `/admin/clear-users` | POST | Admin | Delete all non-admin users |
| `/admin/reorder` | POST | Admin | Reorder queue |
| `/admin/settings` | GET/POST | Admin | Toggle scoring |
| `/admin/settings/leaderboard` | GET/POST | Admin | Toggle leaderboard |
| `/admin/settings/consecutive` | GET/POST | Admin | Queue limit (1–16) |

---

## ☕ Support

Cloud-DJ is free and open source. If you find it useful, consider supporting the project:

[![Patreon](https://img.shields.io/badge/Patreon-NRVZ-ff424d?logo=patreon&logoColor=white)](https://www.patreon.com/c/NRVZ)

Your support helps keep the project maintained and growing.

---

## 📄 License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Attribution-NonCommercial 4.0 International

Built with ❤️ for shared spaces.
