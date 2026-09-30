#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${AIOS_RUNTIME_DIR:-/tmp/aios-runtime}"

if [[ -d "$RUNTIME" ]]; then
  for pidfile in "$RUNTIME"/*.pid; do
    [[ -f "$pidfile" ]] || continue
    pid=$(cat "$pidfile" 2>/dev/null || true)
    name=$(basename "$pidfile" .pid)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "[stop-stack] kill $name pid=$pid"
      kill "$pid" 2>/dev/null || true
      sleep 0.1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
  # stale sockets
  for s in "$RUNTIME"/*.sock; do
    [[ -e "$s" ]] && rm -f "$s"
  done
fi

# Also kill by known entrypoint names if leftover
pkill -f 'aios-policy|ai-engined|/dcpd|agentd|aios-store|aios-scheduler|/rcpd|aios-gateway' 2>/dev/null || true
echo "[stop-stack] done"
