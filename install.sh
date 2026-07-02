#!/usr/bin/env bash
#
# One-click installer for the Blined Cloud VPS deployer Discord bot.
# Run this ON THE MACHINE THAT WILL RUN THE BOT (can be the Proxmox host
# itself, or any Linux box that can reach your Proxmox API over the network).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/krishdeep0009-glitch/real-vps-bot/main/install.sh | bash
#   OR, from a local clone:
#   chmod +x install.sh && ./install.sh
#
set -euo pipefail

REPO_URL="https://github.com/krishdeep0009-glitch/real-vps-bot.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/real-vps-bot}"
SERVICE_NAME="blined-cloud-bot"

echo "=============================================="
echo "  Blined Cloud VPS Deployer — One-Click Setup"
echo "=============================================="

# ---------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
    echo "[1/6] Installing system packages (git, python3, venv, pip)..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq git python3 python3-venv python3-pip >/dev/null
else
    echo "[1/6] Non-Debian system detected — please make sure git, python3,"
    echo "      python3-venv and pip are installed manually, then re-run."
fi

# ---------------------------------------------------------------
# 2. Get the code
# ---------------------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[2/6] Existing install found at $INSTALL_DIR — pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "[2/6] Cloning repo into $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ---------------------------------------------------------------
# 3. Python virtual environment + dependencies
# ---------------------------------------------------------------
echo "[3/6] Creating virtual environment and installing Python dependencies..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

# ---------------------------------------------------------------
# 4. .env setup
# ---------------------------------------------------------------
echo "[4/6] Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "      Created .env from .env.example."
    echo "      >>> You MUST edit $INSTALL_DIR/.env before starting the bot <<<"
    echo "      (Discord token, Proxmox host/token, OS template IDs, etc.)"
else
    echo "      .env already exists — leaving it untouched."
fi

# ---------------------------------------------------------------
# 5. Optional: systemd service for auto-start / auto-restart
# ---------------------------------------------------------------
echo "[5/6] Setting up systemd service (requires sudo)..."
if command -v systemctl >/dev/null 2>&1; then
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Blined Cloud VPS Deployer Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/bot.py
Restart=on-failure
RestartSec=5
EnvironmentFile=$INSTALL_DIR/.env

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
    echo "      Service installed as '${SERVICE_NAME}'."
    echo "      Start it any time with: sudo systemctl start ${SERVICE_NAME}"
else
    echo "      systemctl not found — skipping service setup. Run the bot"
    echo "      manually with: source .venv/bin/activate && python bot.py"
fi

# ---------------------------------------------------------------
# 6. Done
# ---------------------------------------------------------------
echo "[6/6] Install complete."
echo ""
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/.env with your Discord token + Proxmox details."
echo "  2. Prepare your Proxmox cloud-init OS templates (see README.md)."
echo "  3. Start the bot:"
echo "       sudo systemctl start ${SERVICE_NAME}     # if systemd is available"
echo "     or manually:"
echo "       cd $INSTALL_DIR && source .venv/bin/activate && python bot.py"
echo ""
echo "Check status/logs any time with:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
