#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_OWNER="$(stat -c '%U' "${PROJECT_DIR}")"
PLAYER_USER="${1:-${SUDO_USER:-${PROJECT_OWNER}}}"
RULE_TEMPLATE="${PROJECT_DIR}/polkit/49-tonie-network-manager.rules.in"
RULE_PATH="/etc/polkit-1/rules.d/49-tonie-network-manager.rules"
AUTH_PATH="${PROJECT_DIR}/parental_auth.json"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo:"
    echo "  sudo $0 [player-user]"
    exit 1
fi

if [[ ! "${PLAYER_USER}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || ! id "${PLAYER_USER}" >/dev/null 2>&1; then
    echo "Player user '${PLAYER_USER}' does not exist or is not a valid local username."
    exit 1
fi

if [[ "${PLAYER_USER}" == "root" ]]; then
    echo "Refusing to install a NetworkManager policy for root."
    echo "Pass the regular user that runs main.py: sudo $0 [player-user]"
    exit 1
fi

if [[ ! -f "${AUTH_PATH}" ]]; then
    echo "Configure the website's parental password before enabling network changes:"
    echo "  python scripts/set-parental-password.py"
    exit 1
fi

if [[ "$(stat -c '%U' "${AUTH_PATH}")" != "${PLAYER_USER}" ]] || [[ "$(stat -c '%a' "${AUTH_PATH}")" != "600" ]]; then
    echo "${AUTH_PATH} must be owned by ${PLAYER_USER} with permissions 600."
    exit 1
fi

if [[ ! -d /etc/polkit-1/rules.d ]]; then
    echo "PolicyKit is not installed; expected /etc/polkit-1/rules.d."
    exit 1
fi

temporary_rule="$(mktemp)"
trap 'rm -f "${temporary_rule}"' EXIT
sed "s/@PLAYER_USER@/${PLAYER_USER}/g" "${RULE_TEMPLATE}" > "${temporary_rule}"
install -o root -g root -m 0644 "${temporary_rule}" "${RULE_PATH}"

echo "Network setup enabled for ${PLAYER_USER}."
echo "The Network page can now save and forget Wi-Fi profiles."
