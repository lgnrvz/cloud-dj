# Cloud DJ

A self-hosted music queue system where **music plays in the browser** of whoever is logged in as admin. Anyone on your local network can paste YouTube links to add songs, request favorites from their loved list, and watch the queue advance automatically.

Perfect for parties, offices, bars, or shared spaces — run it on a Raspberry Pi, an old laptop, or your main desktop, and let guests queue songs from their phones.

## How It Works

```
Guest ──paste YouTube link──> Web App ──queue──> yt-dlp stream ──> Admin's Browser (video + audio)
```

- **Anyone** on the network can paste YouTube links → songs go to a shared queue
- **Admin's browser** is the player — video + audio streams directly in the browser tab
- **Auto-DJ** shuffles through previously played songs when the queue is empty
- **Videoke Scoring** — confetti, applause, score popup (70-100) when a song finishes
- **Leaderboard** — top 10 scores with who requested it and what song

## Features

### For Everyone
- **Paste to add** — paste a YouTube link, song goes straight to the queue
- **♥ Love songs** — save favorites to your personal library
- **Auto-DJ** — plays random songs from history when the queue's empty
- **10-min limit** — songs over 10 minutes are blocked automatically
- **Duplicate prevention** — same URL won't get queued twice
- **Real-time** — new songs appear as people add them
- **Sign up** — create your own account to track loved songs

### For Admins
- **Browser player** — video + audio plays in your browser tab
- **Skip** — skip the current track, queue advances automatically
- **Queue management** — reorder, remove, love from history
- **User management** — view and remove users
- **Clear history** — wipe played songs (but leaderboard scores stay)
- **Videoke toggle** — turn scoring on/off mid-party

### Auto-DJ
When the queue runs dry, Auto-DJ kicks in and shuffles through previously played songs. The moment someone adds a new song, it transitions seamlessly into the real queue.

---

## Installation

### Prerequisites

| Tool | Why |
|------|-----|
| **Python 3.8+** | Flask + app runtime |
| **Node.js** | yt-dlp JS runtime (for YouTube extraction) |
| **ffmpeg** | yt-dlp post-processing (optional but recommended) |
| **yt-dlp** | Downloads YouTube audio/video streams |
| **Git** | Cloning the repository |

---

### 🐧 Linux (any distro)

**One-command install:**
```bash
curl -sSL https://raw.githubusercontent.com/lgnrvz/cloud-dj/main/install.sh | bash
```

**Or manually:**
```bash
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
./install.sh
```

**What it does:**
- Detects your distro (Debian/Fedora/Arch) and installs system deps via apt/dnf/pacman
- Installs yt-dlp if missing
- Creates a Python virtual environment
- Installs Flask and dependencies
- Creates a **systemd service** that starts on boot
- Opens port 5050 in the firewall (ufw/firewalld)
- Starts the server and prints your LAN URL

**Custom port:**
```bash
PORT=9090 ./install.sh
```

---

### 🪟 Windows (10 / 11)

**One-command install (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -c "iwr -useb https://raw.githubusercontent.com/lgnrvz/cloud-dj/main/install.ps1 | iex"
```

**Or manually:**
```powershell
git clone https://github.com/lgnrvz/cloud-dj.git
cd cloud-dj
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Or the lazy way:** Right-click `install.ps1` → **Run with PowerShell**.

**What it does:**
- Checks for Python, Node.js, ffmpeg — installs via **winget** if missing
- Installs yt-dlp via pip
- Creates a Python virtual environment
- Installs Flask and dependencies
- Opens port 5050 in **Windows Firewall**
- Creates a **Scheduled Task** that starts the server on boot
- Creates `start-cloud-dj.bat` as a fallback launcher
- Starts the server and prints your LAN URL

**Custom port:**
```powershell
$env:PORT=9090; powershell -ExecutionPolicy Bypass -File install.ps1
```

---

### After Installation

**Default admin login:**

| User | Password |
|------|----------|
| `admin` | `djadmin123` |

**Access URLs:**

| Location | URL |
|----------|-----|
| Same machine | http://localhost:5050 |
| Local network | http://<your-pc-ip>:5050 |

**Change the admin password after first login!** Go to Admin panel → Users → admin → (no edit yet, you'd need to modify via SQLite or use a future feature).

---

## Usage

### Adding a Song
1. Open the web app on any device on the network
2. Sign up or log in as admin
3. Paste a YouTube link in the input box and hit Enter/Add
4. Song appears in the queue. When it reaches the front, the admin's browser plays it.

### Admin Panel
- Log in as `admin` → click **Admin** in the top bar
- **Queue:** reorder (drag), remove, love songs
- **History:** see played songs with request counters, love from here
- **Users:** see all registered users, remove troublemakers
- **Settings:** toggle videoke scoring and leaderboard

### Videoke Scoring
When enabled, after each song a score (70-100) pops up on the admin's screen with:
- Confetti explosion
- Audience applause sound
- Score with Filipino commentary (e.g., "Sobrang galing!", "Walang panama!")

The leaderboard tracks the top 10 scores.

---

## Managing the Server

### Linux (systemd)
```bash
sudo systemctl status cloud-dj   # check if running
sudo systemctl stop cloud-dj     # stop
sudo systemctl start cloud-dj    # start
sudo systemctl restart cloud-dj  # restart
sudo journalctl -u cloud-dj -f   # follow logs
```

### Windows
```powershell
# Start
.\start-cloud-dj.bat

# Stop: Task Manager → End "Python" process

# Auto-start: Task Scheduler → Task Scheduler Library → CloudDJ

# Follow logs
Get-Content "$env:USERPROFILE\cloud-dj\server.log" -Wait
```

---

## Updating

### Linux
```bash
cd ~/cloud-dj
git pull
./install.sh   # re-runs setup (won't break config)
```

### Windows
```powershell
cd $env:USERPROFILE\cloud-dj
git pull
powershell -ExecutionPolicy Bypass -File install.ps1
```

---

## Project Structure

```
cloud-dj/
├── app.py                    # Flask application
├── install.sh                # Linux installer
├── install.ps1               # Windows installer
├── requirements.txt          # Python dependencies
├── static/
│   └── applause.wav          # Audience clapping sound effect
├── templates/
│   ├── base.html             # Base layout
│   ├── queue.html            # Main queue page with browser player
│   ├── admin.html            # Admin panel
│   ├── login.html            # Login page
│   └── signup.html           # Registration page
├── .gitignore
└── README.md
```

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | — | Redirects to queue |
| `/queue` | GET | Login | Main queue page with player |
| `/admin` | GET | Admin | Admin panel |
| `/login` | GET/POST | — | Login |
| `/signup` | GET/POST | — | Register |
| `/logout` | GET | Login | Logout |
| `/add` | POST | Login | Add song to queue |
| `/now-playing` | GET | — | Current song (JSON) |
| `/advance` | POST | Login | Advance to next track |
| `/skip` | GET | Admin | Skip current track |
| `/direct-video` | GET | — | Direct stream URL |
| `/love/<id>` | POST | Login | Toggle love |
| `/loved/add/<id>` | POST | Login | Queue from loved |
| `/scoring-enabled` | GET | — | Videoke toggle state |
| `/score/save` | POST | Login | Save score |
| `/leaderboard` | GET | — | Top 10 scores |
| `/admin/history` | GET | Admin | Paginated history |
| `/admin/remove/<id>` | POST | Admin | Remove queue item |
| `/admin/clear-history` | POST | Admin | Delete all played |
| `/admin/settings` | GET/POST | Admin | Toggle scoring |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| yt-dlp: "JS runtime not found" | Install Node.js. On Windows, restart the installer. On Linux, `sudo apt install nodejs` |
| Video won't play | Update yt-dlp: `pip install -U yt-dlp` |
| "Click play" message | Click the video player once — subsequent tracks auto-play |
| Queue stuck on "playing" | Server auto-cleans stale entries on next track advance |
| Port 5050 already in use | `PORT=9090 ./install.sh` on Linux or `$env:PORT=9090` on Windows |
| Can't access from other devices | Check firewall: Linux → `ufw allow 5050`, Windows → check Windows Defender Firewall |
| Can't reach LAN URL | Make sure both devices are on the **same network**. No guest network separation. |

---

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Attribution-NonCommercial 4.0 International
