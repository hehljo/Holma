#!/usr/bin/env bash
# ============================================================================
# BackupGenie - USB Auto-Backup Trigger Script
# Triggered by systemd/udev when a USB drive is connected
#
# Features:
#   - Auto-mount detection and fallback
#   - Filesystem type detection via blkid
#   - Concurrent execution prevention via flock
#   - API call retry with backoff
#   - Free space verification
# ============================================================================

set -euo pipefail

# --- Configuration ---
BACKUP_MOUNT="${BACKUP_MOUNT:-/mnt/backup}"
API_URL="${BACKUP_API_URL:-http://localhost:5000/api/v1/backup/start}"
TOKEN_FILE="${BACKUP_TOKEN_FILE:-/etc/backupgenie/api_token}"
LOG_DIR="${BACKUP_LOG_DIR:-/var/log/backupgenie}"
LOCK_FILE="/var/run/backupgenie-trigger.lock"
MIN_FREE_SPACE_MB="${MIN_FREE_SPACE_MB:-500}"
MAX_RETRIES=5
RETRY_DELAY=3

# Device passed by udev (e.g. /dev/sda1)
DEVICE="${1:-}"

# --- Functions ---

log() {
    local level="$1"
    shift
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$timestamp] [$level] $*" | tee -a "$LOG_DIR/trigger.log"
}

check_dependencies() {
    local missing=()
    for cmd in curl blkid findmnt docker; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log "ERROR" "Missing dependencies: ${missing[*]}"
        exit 1
    fi
}

get_api_token() {
    # Try token file first, then environment variable
    if [[ -f "$TOKEN_FILE" ]]; then
        cat "$TOKEN_FILE"
    elif [[ -n "${BACKUP_API_TOKEN:-}" ]]; then
        echo "$BACKUP_API_TOKEN"
    else
        log "ERROR" "No API token found. Set BACKUP_API_TOKEN or create $TOKEN_FILE"
        exit 1
    fi
}

detect_and_mount() {
    # Check if backup path is already mounted
    if findmnt -M "$BACKUP_MOUNT" &>/dev/null; then
        log "INFO" "Backup path already mounted: $BACKUP_MOUNT"
        return 0
    fi

    # If no device specified, try to find backup partition by label
    if [[ -z "$DEVICE" ]]; then
        log "INFO" "No device specified, looking for labeled partition 'BACKUP' or 'backupgenie'"
        DEVICE=$(blkid -L "BACKUP" 2>/dev/null || blkid -L "backupgenie" 2>/dev/null || true)
        if [[ -z "$DEVICE" ]]; then
            log "ERROR" "No backup device found. Label a partition 'BACKUP' or pass device as argument."
            exit 1
        fi
    fi

    # Wait for device to settle
    sleep 2

    # Detect filesystem type
    local fstype
    fstype=$(blkid -s TYPE -o value "$DEVICE" 2>/dev/null || true)

    if [[ -z "$fstype" ]]; then
        log "ERROR" "Cannot detect filesystem type for $DEVICE"
        exit 1
    fi

    log "INFO" "Detected filesystem: $fstype on $DEVICE"

    # Create mount point if needed
    mkdir -p "$BACKUP_MOUNT"

    # Mount with filesystem-appropriate options
    local mount_opts=""
    case "$fstype" in
        ext4|ext3|ext2)
            mount_opts="-o defaults,noatime"
            ;;
        ntfs|ntfs-3g)
            fstype="ntfs-3g"
            mount_opts="-o rw,uid=1000,gid=1000,umask=0022"
            ;;
        exfat)
            mount_opts="-o rw,uid=1000,gid=1000,umask=0022"
            ;;
        vfat|fat32)
            mount_opts="-o rw,uid=1000,gid=1000,umask=0022"
            ;;
        btrfs)
            mount_opts="-o defaults,noatime,compress=zstd"
            ;;
        xfs)
            mount_opts="-o defaults,noatime"
            ;;
        *)
            mount_opts="-o defaults"
            ;;
    esac

    if mount -t "$fstype" $mount_opts "$DEVICE" "$BACKUP_MOUNT"; then
        log "INFO" "Mounted $DEVICE ($fstype) on $BACKUP_MOUNT"
    else
        log "ERROR" "Failed to mount $DEVICE on $BACKUP_MOUNT"
        exit 1
    fi
}

check_free_space() {
    local free_mb
    free_mb=$(df -BM "$BACKUP_MOUNT" | tail -1 | awk '{print $4}' | sed 's/M//')

    if [[ "$free_mb" -lt "$MIN_FREE_SPACE_MB" ]]; then
        log "ERROR" "Insufficient free space: ${free_mb}MB (minimum: ${MIN_FREE_SPACE_MB}MB)"
        exit 1
    fi

    log "INFO" "Free space: ${free_mb}MB"
}

check_backend_ready() {
    # Check if the Docker container is running
    if ! docker ps --filter "name=backupgenie" --filter "status=running" -q | grep -q .; then
        log "WARN" "BackupGenie backend container not running, waiting..."
        local waited=0
        while [[ $waited -lt 60 ]]; do
            sleep 5
            waited=$((waited + 5))
            if docker ps --filter "name=backupgenie" --filter "status=running" -q | grep -q .; then
                log "INFO" "Backend container is now running"
                return 0
            fi
        done
        log "ERROR" "Backend container did not start within 60 seconds"
        return 1
    fi
    return 0
}

trigger_backup() {
    local token
    token=$(get_api_token)

    local attempt=0
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))
        log "INFO" "Triggering backup (attempt $attempt/$MAX_RETRIES)..."

        local response
        local http_code
        response=$(curl -s -w "\n%{http_code}" \
            -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $token" \
            -d '{}' \
            --connect-timeout 10 \
            --max-time 30 \
            2>&1) || true

        http_code=$(echo "$response" | tail -1)
        local body
        body=$(echo "$response" | sed '$d')

        if [[ "$http_code" =~ ^2 ]]; then
            log "INFO" "Backup triggered successfully: $body"

            # Send desktop notification if available
            if command -v notify-send &>/dev/null; then
                notify-send "BackupGenie" "Backup started automatically" --icon=drive-harddisk 2>/dev/null || true
            fi

            return 0
        fi

        log "WARN" "API returned HTTP $http_code: $body"

        if [[ $attempt -lt $MAX_RETRIES ]]; then
            local wait=$((RETRY_DELAY * attempt))
            log "INFO" "Retrying in ${wait}s..."
            sleep "$wait"
        fi
    done

    log "ERROR" "Failed to trigger backup after $MAX_RETRIES attempts"

    # Send failure notification
    if command -v notify-send &>/dev/null; then
        notify-send "BackupGenie" "Auto-backup failed to start!" --icon=dialog-error --urgency=critical 2>/dev/null || true
    fi

    return 1
}

# --- Main ---

# Ensure log directory exists
mkdir -p "$LOG_DIR"

log "INFO" "=== BackupGenie trigger started ==="
log "INFO" "Device: ${DEVICE:-auto-detect}"

# Prevent concurrent executions
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log "WARN" "Another backup trigger is already running. Exiting."
    exit 0
fi

# Check dependencies
check_dependencies

# Detect and mount backup drive
detect_and_mount

# Verify free space
check_free_space

# Wait for backend
if ! check_backend_ready; then
    exit 1
fi

# Trigger the backup
trigger_backup

log "INFO" "=== BackupGenie trigger completed ==="
