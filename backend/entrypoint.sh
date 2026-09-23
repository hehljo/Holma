#!/bin/bash
# BackupGenie - Container Entrypoint
# Runs hardware detection and starts the application

set -e

# Source hardware detection (sets environment variables)
source /app/scripts/detect-hardware.sh

# Set MAX_PARALLEL_TASKS if not explicitly configured
if [ -z "$MAX_PARALLEL_TASKS" ] || [ "$MAX_PARALLEL_TASKS" = "auto" ]; then
    export MAX_PARALLEL_TASKS="$RECOMMENDED_PARALLEL_TASKS"
    echo "  Auto-configured MAX_PARALLEL_TASKS=$MAX_PARALLEL_TASKS"
fi

# Adjust gunicorn workers based on available resources
GUNICORN_WORKERS=${GUNICORN_WORKERS:-2}
if [ "${HARDWARE_RAM_MB:-0}" -gt 0 ] && [ "${HARDWARE_RAM_MB:-0}" -le 1024 ]; then
    GUNICORN_WORKERS=1
    echo "  Low RAM detected, using 1 gunicorn worker"
fi

echo ""
echo "Starting BackupGenie backend..."

# Backups run only in this dedicated process. API workers merely enqueue jobs,
# so gunicorn worker restarts cannot lose an active job or break stop requests.
python -m app.backup.worker &
JOB_WORKER_PID=$!
echo "  Backup worker started (pid $JOB_WORKER_PID)"

# The scheduler also only queues jobs and runs once per container.
SCHEDULER_PID=""
if [ "${SCHEDULER_ENABLED:-true}" = "true" ]; then
    python -m app.scheduler.runner &
    SCHEDULER_PID=$!
    echo "  Backup scheduler started (pid $SCHEDULER_PID)"
else
    echo "  Backup scheduler disabled (SCHEDULER_ENABLED=false)"
fi

shutdown() {
    if [ -n "$SCHEDULER_PID" ]; then
        kill "$SCHEDULER_PID" 2>/dev/null || true
    fi
    if [ -n "$GUNICORN_PID" ]; then
        kill "$GUNICORN_PID" 2>/dev/null || true
    fi
    if [ -n "$JOB_WORKER_PID" ]; then
        kill "$JOB_WORKER_PID" 2>/dev/null || true
    fi
}
trap shutdown TERM INT

gunicorn \
    --bind 0.0.0.0:5000 \
    --workers "$GUNICORN_WORKERS" \
    --timeout 300 \
    run:app &
GUNICORN_PID=$!

# Exit and let the container restart if any required process dies.
PIDS=("$JOB_WORKER_PID" "$GUNICORN_PID")
if [ -n "$SCHEDULER_PID" ]; then
    PIDS+=("$SCHEDULER_PID")
fi

set +e
wait -n "${PIDS[@]}"
EXIT_CODE=$?
set -e
shutdown
wait "${PIDS[@]}" 2>/dev/null || true
exit "$EXIT_CODE"
