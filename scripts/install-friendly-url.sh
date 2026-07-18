#!/usr/bin/env bash
set -euo pipefail

FRIENDLY_NAME="${1:-tonie}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo:"
    echo "  sudo $0 [hostname]"
    exit 1
fi

if [[ ! "${FRIENDLY_NAME}" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
    echo "Hostname must contain only lowercase letters, numbers, and interior hyphens."
    exit 1
fi

if [[ ! -x /usr/lib/systemd/systemd-socket-proxyd ]]; then
    echo "systemd-socket-proxyd is not installed on this system."
    exit 1
fi

if ! command -v avahi-daemon >/dev/null 2>&1; then
    echo "Avahi is required. Install it first with: sudo apt install avahi-daemon"
    exit 1
fi

hostnamectl set-hostname "${FRIENDLY_NAME}"
install -m 0644 "${PROJECT_DIR}/systemd/tonie-web.socket" /etc/systemd/system/tonie-web.socket
install -m 0644 "${PROJECT_DIR}/systemd/tonie-web.service" /etc/systemd/system/tonie-web.service

systemctl daemon-reload
systemctl enable --now avahi-daemon.service
systemctl restart avahi-daemon.service
systemctl enable --now tonie-web.socket
"${PROJECT_DIR}/scripts/install-network-permissions.sh" "${SUDO_USER:-$(stat -c '%U' "${PROJECT_DIR}")}"

echo
echo "Friendly URL installed. Open http://${FRIENDLY_NAME}.local"
echo "The player will remain available at http://${FRIENDLY_NAME}.local:5000 as a fallback."
