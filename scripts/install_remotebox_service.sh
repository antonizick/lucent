#!/bin/bash
# One-time install of the RemoteBox auto-mount systemd service.
# Run manually: ./scripts/install_remotebox_service.sh — will prompt for your sudo password.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sudo cp "$REPO_DIR/scripts/lucent-rclone-remotebox.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lucent-rclone-remotebox.service

echo "Done. Status:"
systemctl status lucent-rclone-remotebox.service --no-pager
