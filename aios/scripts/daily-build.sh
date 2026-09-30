#!/usr/bin/env bash
# Daily build: test → deb → img skeleton → report
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE=$(date +%Y%m%d)
OUT="${DAILY_OUT:-$ROOT/dist/daily-$DATE}"
mkdir -p "$OUT"
export AIOS_HEADLESS=1 AIOS_OFFLINE=1 AIOS_RCP_LOOPBACK=1
export PATH="$ROOT/.venv/bin:$PATH"

{
  echo "# luminOS daily build $DATE"
  echo "host: $(hostname)"
  echo "arch: $(uname -m)"
  echo "started: $(date -Iseconds)"
} | tee "$OUT/BUILD_INFO.txt"

if [[ ! -x .venv/bin/python ]]; then
  make venv
else
  .venv/bin/pip install -e ".[dev]" -q
fi

make stop || true
set +e
make test 2>&1 | tee "$OUT/test.log"
TEST_RC=${PIPESTATUS[0]}
set -e

set +e
bash scripts/smoke.sh 2>&1 | tee "$OUT/smoke.log"
SMOKE_RC=${PIPESTATUS[0]}
set -e

set +e
bash packaging/build-deb.sh 2>&1 | tee "$OUT/deb.log"
DEB_RC=${PIPESTATUS[0]}
set -e
cp -a dist/*.deb "$OUT/" 2>/dev/null || true

set +e
bash scripts/mkimg/build-skeleton.sh 2>&1 | tee "$OUT/img.log"
IMG_RC=${PIPESTATUS[0]}
set -e

# live-build config freeze (does not require root for packaging the config tree)
mkdir -p "$OUT/live-build-config"
cp -a live-build/* "$OUT/live-build-config/" 2>/dev/null || true

cat >"$OUT/SUMMARY.md" <<EOF
# Daily build summary — $DATE

| Step | RC |
|------|----|
| unit+integration | $TEST_RC |
| smoke | $SMOKE_RC |
| deb | $DEB_RC |
| img-skeleton | $IMG_RC |

Artifacts in \`$OUT\`.
EOF

echo "Daily build done → $OUT (test=$TEST_RC smoke=$SMOKE_RC deb=$DEB_RC img=$IMG_RC)"
# Fail the daily job if tests/smoke fail; deb/img may need root tooling
if [[ $TEST_RC -ne 0 || $SMOKE_RC -ne 0 ]]; then
  exit 1
fi
exit 0
