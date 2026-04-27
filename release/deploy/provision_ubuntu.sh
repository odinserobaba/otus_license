#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

APP_DIR="/opt/normatives"
APP_USER="${SUDO_USER:-$(logname 2>/dev/null || echo ubuntu)}"

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx git curl

if [[ ! -d "$APP_DIR" ]]; then
  echo "Expected app directory not found: $APP_DIR"
  echo "Clone project first: git clone <repo_url> $APP_DIR"
  exit 1
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

sudo -u "$APP_USER" bash -lc "
  cd '$APP_DIR'
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
"

echo "Bootstrap completed."
echo "Next:"
echo "1) Fill $APP_DIR/.env.final"
echo "2) Enable systemd service + nginx config from release/deploy/"
