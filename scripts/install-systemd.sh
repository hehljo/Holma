#!/usr/bin/env bash
# ============================================================================
# BackupGenie - Systemd & Udev Installation Script
# Supports: Raspberry Pi, Ubuntu/Debian, and other systemd-based Linux distros
#
# Installs:
#   - udev rule for USB auto-detection
#   - systemd service for backup triggering
#   - auto-mount service for backup drives
# ============================================================================

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_USER="${SUDO_USER:-$(whoami)}"
TRIGGER_SCRIPT="$SCRIPT_DIR/trigger-backup.sh"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Pre-checks ---

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

if ! command -v systemctl &>/dev/null; then
    log_error "systemd is required. This script does not support other init systems."
    exit 1
fi

# --- Install udev rule ---

log_info "Installing udev rule for USB auto-detection..."

cat > /etc/udev/rules.d/99-backupgenie-backup.rules << 'EOF'
# BackupGenie - Auto-trigger backup on USB device connection
# Matches USB block devices (partitions) when added
ACTION=="add", SUBSYSTEM=="block", ENV{ID_USB_DRIVER}=="usb-storage", \
    ENV{DEVTYPE}=="partition", \
    TAG+="systemd", ENV{SYSTEMD_WANTS}="backupgenie-backup@%k.service"
EOF

# --- Install systemd service ---

log_info "Installing systemd backup trigger service..."

cat > /etc/systemd/system/backupgenie-backup@.service << EOF
[Unit]
Description=BackupGenie Auto-Backup Trigger for %i
After=docker.service network-online.target
Wants=network-online.target
ConditionPathExists=$TRIGGER_SCRIPT

[Service]
Type=oneshot
ExecStart=$TRIGGER_SCRIPT /dev/%i
User=root
Group=root

# Environment
Environment=BACKUP_MOUNT=/mnt/backup
Environment=BACKUP_API_URL=http://localhost:5000/api/v1/backup/start
Environment=BACKUP_TOKEN_FILE=/etc/backupgenie/api_token

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=backupgenie-trigger

# Security hardening
ProtectSystem=strict
ReadWritePaths=/mnt/backup /var/log/backupgenie /var/run
PrivateTmp=true

# Timeout (allow long backups)
TimeoutStartSec=21600

[Install]
WantedBy=multi-user.target
EOF

# --- Create directories ---

log_info "Creating required directories..."

mkdir -p /etc/backupgenie
mkdir -p /var/log/backupgenie
mkdir -p /mnt/backup

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" /var/log/backupgenie
chmod 755 "$TRIGGER_SCRIPT"

# --- API Token Setup ---

if [[ ! -f /etc/backupgenie/api_token ]]; then
    log_warn "API token file not found at /etc/backupgenie/api_token"
    echo ""
    echo "  To generate a token:"
    echo "    sudo python3 $SCRIPT_DIR/create-api-token.py"
    echo "  The helper asks for the admin password and writes mode 0600."
    echo ""
else
    chmod 600 /etc/backupgenie/api_token
    log_info "API token file found and permissions secured"
fi

# --- Reload systemd ---

log_info "Reloading systemd and udev..."

systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger

# --- Enable service ---

log_info "Enabling backup trigger service..."
systemctl enable "backupgenie-backup@.service" 2>/dev/null || true

# --- Summary ---

echo ""
echo "============================================"
echo "  BackupGenie Auto-Backup Setup Complete"
echo "============================================"
echo ""
echo "  udev rule:    /etc/udev/rules.d/99-backupgenie-backup.rules"
echo "  systemd unit: /etc/systemd/system/backupgenie-backup@.service"
echo "  trigger:      $TRIGGER_SCRIPT"
echo "  token file:   /etc/backupgenie/api_token"
echo "  log dir:      /var/log/backupgenie/"
echo "  mount point:  /mnt/backup"
echo ""
echo "  To test manually:"
echo "    sudo systemctl start backupgenie-backup@sda1"
echo ""
echo "  To view logs:"
echo "    journalctl -u 'backupgenie-backup@*' -f"
echo "    tail -f /var/log/backupgenie/trigger.log"
echo ""

log_info "Done! Plug in a USB drive to test auto-backup."
