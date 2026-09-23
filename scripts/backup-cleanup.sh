#!/bin/bash
# Holma - Cleanup Script
# Removes old backups and logs based on retention policy

set -e

LOG_FILE="/var/log/holma-cleanup.log"
BACKUP_BASE_PATH="${BACKUP_BASE_PATH:-/mnt/backup}"
RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
DRY_RUN="${DRY_RUN:-false}"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "============================================"
log "Cleanup started (retention: $RETENTION_DAYS days)"

if [ "$DRY_RUN" = "true" ]; then
    log "DRY RUN MODE - No files will be deleted"
fi

# Cleanup old log files
log "Cleaning up old log files..."
if [ -d "/var/log/holma" ]; then
    find_cmd="find /var/log/holma -name '*.log' -type f -mtime +$RETENTION_DAYS"

    if [ "$DRY_RUN" = "true" ]; then
        count=$(eval "$find_cmd" | wc -l)
        log "Would delete $count log files"
        eval "$find_cmd" -ls
    else
        eval "$find_cmd" -delete
        log "Deleted old log files"
    fi
fi

# Cleanup database entries via API (if available)
if docker ps | grep -q holma-backend; then
    log "Cleaning up old database entries..."
    docker exec holma-backend python3 -c "
from app import create_app, db
from app.models.backup import Backup
from datetime import datetime, timedelta

app = create_app()
with app.app_context():
    cutoff_date = datetime.utcnow() - timedelta(days=$RETENTION_DAYS)
    old_backups = Backup.query.filter(Backup.started_at < cutoff_date).all()

    print(f'Found {len(old_backups)} old backup records')

    if '$DRY_RUN' != 'true':
        for backup in old_backups:
            db.session.delete(backup)
        db.session.commit()
        print('Deleted old backup records')
    else:
        print('DRY RUN: Would delete these records')
" 2>&1 | tee -a "$LOG_FILE"
fi

# Calculate disk usage
if [ -d "$BACKUP_BASE_PATH" ]; then
    log "Current backup disk usage:"
    du -sh "$BACKUP_BASE_PATH"/* 2>/dev/null | tee -a "$LOG_FILE" || log "No backups found"

    log "Total backup size:"
    du -sh "$BACKUP_BASE_PATH" | tee -a "$LOG_FILE"
fi

log "Cleanup completed"
log "============================================"
