#!/usr/bin/env bash
set -euo pipefail

# =========================================================
#           Cloud-DJ — Desktop Installer
#  Turns any Linux machine into a LAN music server
# =========================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Config ──────────────────────────────────────────────────
INSTALL_DIR="${1:-$HOME/cloud-dj}"
PORT="${PORT:-5050}"
REPO="https://github.com/lgnrvz/cloud-dj.git"
SERVICE_NAME="cloud-dj"

# ── Banner ──────────────────────────────────────────────────
echo ""
echo -e "${CYAN}  ___ _                 _   ${GREEN}  ___ ___  ${NC}"
echo -e "${CYAN} / __| |_   __ _ _ _  __| | ${GREEN} / __/ _ \ ${NC}"
echo -e "${CYAN}| (__| ' \ / _\` | ' \/ _\` | ${GREEN}| (_| (_) |${NC}"
echo -e "${CYAN} \___|_||_|\__,_|_||_\__,_| ${GREEN} \___\__\_\ ${NC}"
echo -e "${YELLOW}  LAN Music Server Installer${NC}"

# ── Step 1: Check OS ────────────────────────────────────────
if [ "$(uname)" != "Linux" ]; then
    err "This installer is for Linux only. Detected: $(uname)"
    exit 1
fi

DISTRO=""
if command -v apt &>/dev/null; then
    DISTRO="debian"
elif command -v dnf &>/dev/null; then
    DISTRO="fedora"
elif command -v pacman &>/dev/null; then
    DISTRO="arch"
else
    warn "Unknown package manager. You may need to install dependencies manually."
fi

# ── Step 2: Install System Dependencies ──────────────────────
info "Checking system dependencies..."

MISSING_PKGS=()

# Python 3
if ! command -v python3 &>/dev/null; then
    MISSING_PKGS+=("python3" "python3-pip" "python3-venv")
fi

# pip3
if ! python3 -c "import ensurepip" &>/dev/null 2>&1; then
    MISSING_PKGS+=("python3-pip" "python3-venv")
fi

# venv
if ! python3 -c "import venv" &>/dev/null 2>&1; then
    MISSING_PKGS+=("python3-venv")
fi

# Node.js (for yt-dlp JS runtime)
if ! command -v node &>/dev/null && ! command -v nodejs &>/dev/null; then
    MISSING_PKGS+=("nodejs")
fi

# ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    MISSING_PKGS+=("ffmpeg")
fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    case "$DISTRO" in
        debian)
            warn "Installing: ${MISSING_PKGS[*]}"
            sudo apt update
            sudo apt install -y "${MISSING_PKGS[@]}"
            ;;
        fedora)
            warn "Installing: ${MISSING_PKGS[*]}"
            sudo dnf install -y "${MISSING_PKGS[@]}"
            ;;
        arch)
            warn "Installing: ${MISSING_PKGS[*]}"
            sudo pacman -S --needed --noconfirm "${MISSING_PKGS[@]}"
            ;;
        *)
            err "Unknown distro. Install manually: ${MISSING_PKGS[*]}"
            exit 1
            ;;
    esac
    ok "System dependencies installed"
else
    ok "All system dependencies already met"
fi

# ── Step 3: Install yt-dlp (if missing) ──────────────────────
if ! command -v yt-dlp &>/dev/null; then
    info "Installing yt-dlp..."
    # Try pip3 first (may fail on PEP 668 systems like Raspberry Pi OS)
    if command -v pip3 &>/dev/null; then
        pip3 install --user yt-dlp 2>/dev/null || true
    fi
    # If pip3 failed or isn't available, download directly
    if ! command -v yt-dlp &>/dev/null; then
        info "pip3 install failed — downloading yt-dlp directly..."
        sudo curl -#L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
        sudo chmod a+rx /usr/local/bin/yt-dlp
    fi
    ok "yt-dlp installed"
else
    ok "yt-dlp already installed ($(command -v yt-dlp))"
fi

# Ensure ~/.local/bin is on PATH (for pip --user installs)
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    warn "Adding ~/.local/bin to PATH (add this to your ~/.bashrc or ~/.zshrc)"
fi

# ── Step 4: Clone / Pull the App ─────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    info "Updating existing installation at $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    if git rev-parse --git-dir &>/dev/null 2>&1; then
        git pull --ff-only
        ok "Repository updated"
    else
        warn "$INSTALL_DIR exists but isn't a git repo. Using as-is."
    fi
else
    info "Cloning Cloud-DJ to $INSTALL_DIR..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "Repository cloned"
fi

cd "$INSTALL_DIR"

# ── Step 5: Set up Python Virtual Environment ────────────────
info "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

info "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

# Also install yt-dlp in the venv as a fallback
.venv/bin/pip install yt-dlp --quiet

ok "Python dependencies installed"

# ── Step 6: Verify paths work ────────────────────────────────
info "Verifying installation..."
NODE_OK=$(command -v node || command -v nodejs || echo "NOT_FOUND")
YTDLP_OK=$(command -v yt-dlp || echo "NOT_FOUND")
FFMPEG_OK=$(command -v ffmpeg || echo "NOT_FOUND")

if [ "$NODE_OK" = "NOT_FOUND" ]; then
    warn "Node.js not found — yt-dlp may fall back to Python JS runtime (slower)"
else
    ok "Node.js: $NODE_OK"
fi

if [ "$YTDLP_OK" = "NOT_FOUND" ]; then
    # Check if venv has it
    if [ -f ".venv/bin/yt-dlp" ]; then
        YTDLP_OK=".venv/bin/yt-dlp"
        ok "yt-dlp (venv): $YTDLP_OK"
    else
        warn "yt-dlp not found — install manually with: pip install yt-dlp"
    fi
else
    ok "yt-dlp: $YTDLP_OK"
fi

if [ "$FFMPEG_OK" = "NOT_FOUND" ]; then
    warn "ffmpeg not found — install for best compatibility"
else
    ok "ffmpeg: $FFMPEG_OK"
fi

# ── Step 7: Create systemd Service ───────────────────────────
info "Setting up systemd service..."

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > /tmp/cloud-dj.service << SERVICEEOF
[Unit]
Description=Cloud-DJ — LAN Music Server
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python app.py
Restart=always
RestartSec=5
Environment=PORT=$PORT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

if [ -f "$SERVICE_FILE" ]; then
    warn "Service file already exists — updating..."
    sudo cp /tmp/cloud-dj.service "$SERVICE_FILE"
else
    info "Installing systemd service..."
    sudo cp /tmp/cloud-dj.service "$SERVICE_FILE"
fi

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

ok "systemd service created & started (${SERVICE_NAME})"

# ── Step 8: Firewall ─────────────────────────────────────────
info "Opening port $PORT in firewall..."

if command -v ufw &>/dev/null; then
    sudo ufw allow "$PORT/tcp" 2>/dev/null || true
    ok "ufw: port $PORT opened"
elif command -v firewall-cmd &>/dev/null; then
    sudo firewall-cmd --permanent --add-port="$PORT/tcp" 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
    ok "firewalld: port $PORT opened"
else
    warn "No firewall tool detected (ufw/firewalld). Ensure port $PORT is open manually."
fi

# ── Step 9: Get LAN IP ───────────────────────────────────────
info "Detecting LAN address..."
LAN_IP=$(ip -4 addr show | grep -oP '(?<=inet )192\.168\.\d+\.\d+' | head -1)
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

# ── Step 10: Wait for service and verify ────────────────────
info "Waiting for server to start..."
sleep 3

if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
    ok "Server is running and responding!"
else
    warn "Server may not be ready yet. Checking logs..."
    sudo journalctl -u "${SERVICE_NAME}.service" --no-pager -n 10 --since "30 seconds ago" || true
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}             INSTALLATION COMPLETE!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo -e "  ${CYAN}Local access:${NC}    http://localhost:$PORT"
echo -e "  ${CYAN}LAN access:${NC}      http://${LAN_IP}:$PORT"
echo -e "  ${CYAN}Admin user:${NC}      admin"
echo -e "  ${CYAN}Admin pass:${NC}      djadmin123"
echo ""
echo -e "  ${YELLOW}Other devices on your network can access:${NC}"
echo -e "  ${CYAN}  http://${LAN_IP}:$PORT${NC}"
echo ""
echo -e "  ${YELLOW}Commands:${NC}"
echo -e "    sudo systemctl status ${SERVICE_NAME}  — check status"
echo -e "    sudo journalctl -u ${SERVICE_NAME} -f  — follow logs"
echo -e "    sudo systemctl stop ${SERVICE_NAME}    — stop server"
echo -e "    sudo systemctl start ${SERVICE_NAME}   — start server"
echo ""
echo -e "  ${YELLOW}To change port:${NC}  PORT=9090 ./install.sh"
echo ""

# Test LAN access
if [ -n "$LAN_IP" ]; then
    if curl -s "http://${LAN_IP}:${PORT}" > /dev/null 2>&1; then
        ok "LAN access confirmed: http://${LAN_IP}:${PORT}"
    fi
fi

echo -e "${GREEN}Happy spinning! 🎧${NC}"
