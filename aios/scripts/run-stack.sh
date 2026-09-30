#!/usr/bin/env bash
# Start luminOS user-session service stack (dev / CI / daily smoke).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AIOS_HEADLESS="${AIOS_HEADLESS:-1}"
export AIOS_RUNTIME_DIR="${AIOS_RUNTIME_DIR:-/tmp/aios-runtime}"
export AIOS_STATE_DIR="${AIOS_STATE_DIR:-/tmp/aios-state}"
export AIOS_CONFIG_DIR="${AIOS_CONFIG_DIR:-/tmp/aios-config}"
export AIOS_RCP_LOOPBACK="${AIOS_RCP_LOOPBACK:-1}"
export AIOS_OFFLINE="${AIOS_OFFLINE:-1}"
mkdir -p "$AIOS_RUNTIME_DIR" "$AIOS_STATE_DIR" "$AIOS_CONFIG_DIR" "$AIOS_RUNTIME_DIR/logs"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
  # Prefer venv entry points
  export PATH="$ROOT/.venv/bin:$PATH"
else
  PY="${PYTHON:-python3}"
fi

bash "$ROOT/scripts/stop-stack.sh" 2>/dev/null || true
sleep 0.2

start_one() {
  local name="$1"
  shift
  echo "[run-stack] starting $name"
  nohup "$@" >"$AIOS_RUNTIME_DIR/logs/${name}.log" 2>&1 &
  echo $! >"$AIOS_RUNTIME_DIR/${name}.pid"
}

start_one policy   aios-policy
start_one ai-engined ai-engined
start_one dcpd     dcpd
start_one agentd   agentd
start_one store    aios-store
start_one scheduler aios-scheduler
start_one rcpd     rcpd --host 127.0.0.1 --port 17420
start_one gateway  aios-gateway --port 18765

# Wait until sockets appear
for i in $(seq 1 50); do
  ok=1
  for s in policy dcpd agentd ai-engined rcpd gateway store scheduler; do
    [[ -S "$AIOS_RUNTIME_DIR/${s}.sock" ]] || ok=0
  done
  [[ $ok -eq 1 ]] && break
  sleep 0.1
done

"$PY" - <<'PY'
import asyncio, os, sys
from aios_common.ipc import call

async def main():
    failed = []
    for s in ["policy", "dcpd", "agentd", "ai-engined", "rcpd", "gateway", "store", "scheduler"]:
        try:
            r = await call(s, "ping", {}, timeout=2)
            assert r.get("ok"), r
            print(f"  OK {s}")
        except Exception as e:
            print(f"  FAIL {s}: {e}")
            failed.append(s)
    if failed:
        sys.exit(1)
    print("[run-stack] all services up")

asyncio.run(main())
PY
