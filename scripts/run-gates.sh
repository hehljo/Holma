#!/usr/bin/env bash
# Runs every quality gate in the repository and reports each one separately.
#
#   PYTHON=/path/to/venv/bin/python scripts/run-gates.sh
#
# Gates are discovered from the directories, not listed here: a new
# backend/tests/test_*.py or scripts/gates/*.py runs without touching this file.
# Exit codes of a gate: 0 passed, 1 failed, 2 not measured. "Not measured" and
# "no gates found" both make the whole run fail.
set -u
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

passed=0; failed=0; unmeasured=0; ran=0

run_gate() {
  local name="$1"; shift
  local output status
  output="$("$@" 2>&1)"
  status=$?
  ran=$((ran + 1))
  case $status in
    0) passed=$((passed + 1)); echo "  ok    $name" ;;
    2) unmeasured=$((unmeasured + 1)); echo "  n/a   $name (nicht gemessen)"; printf '%s\n' "$output" | tail -5 ;;
    *) failed=$((failed + 1)); echo "  ROT   $name (exit $status)"; printf '%s\n' "$output" | tail -15 ;;
  esac
}

echo "Backend"
for test in backend/tests/test_*.py; do
  [ -e "$test" ] || continue
  run_gate "$test" env PYTHONPATH=backend "$PYTHON" "$test"
done

echo "Repository"
for gate in scripts/gates/*.py; do
  [ -e "$gate" ] || continue
  run_gate "$gate" "$PYTHON" "$gate"
done

echo "Frontend"
if [ -d frontend/node_modules ]; then
  run_gate "frontend lint" npm --prefix frontend run --silent lint
  run_gate "frontend build" npm --prefix frontend run --silent build
else
  run_gate "frontend (node_modules fehlt)" sh -c 'exit 2'
fi

echo
echo "Gates: $ran gelaufen · $passed grün · $failed rot · $unmeasured nicht gemessen"
if [ "$ran" -eq 0 ]; then echo "ROT: keine Gates gefunden"; exit 1; fi
[ "$failed" -eq 0 ] && [ "$unmeasured" -eq 0 ]
