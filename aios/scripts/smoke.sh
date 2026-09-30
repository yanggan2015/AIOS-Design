#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export AIOS_HEADLESS=1
export AIOS_RUNTIME_DIR="${AIOS_RUNTIME_DIR:-/tmp/aios-smoke-runtime}"
export AIOS_STATE_DIR="${AIOS_STATE_DIR:-/tmp/aios-smoke-state}"
export AIOS_CONFIG_DIR="${AIOS_CONFIG_DIR:-/tmp/aios-smoke-config}"
export AIOS_RCP_LOOPBACK=1
export AIOS_OFFLINE=1
export PATH="$ROOT/.venv/bin:$PATH"

bash scripts/run-stack.sh

aios ping --services policy,dcpd,agentd,ai-engined,rcpd,gateway
aios dcp act --target fixture:hello --action ime_commit --node w_entry --args-json '{"node":"w_entry","text":"smoke"}'
aios dcp act --target fixture:hello --action click --node w_btn_ok --args-json '{"node":"w_btn_ok"}'
out=$(aios dcp snapshot --target fixture:hello)
echo "$out" | grep -q 'OK:smoke'
aios agent run --goal '在夹具里输入「日构」并点 OK'
echo "[smoke] PASS"
bash scripts/stop-stack.sh
