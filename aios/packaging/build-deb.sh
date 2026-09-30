#!/usr/bin/env bash
# Build luminos-aios .deb (no dpkg-buildpackage required beyond dpkg-deb).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-$(dpkg --print-architecture 2>/dev/null || echo amd64)}"
OUT="${OUT_DIR:-$ROOT/dist}"
STAGE="$OUT/deb-stage"
PKG="luminos-aios_${VERSION}_${ARCH}"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
  "$STAGE/usr/lib/luminos-aios/site-packages" \
  "$STAGE/usr/bin" \
  "$STAGE/lib/systemd/system" \
  "$STAGE/usr/lib/systemd/user" \
  "$STAGE/usr/share/luminos/profiles" \
  "$STAGE/usr/share/luminos/fixtures" \
  "$STAGE/usr/share/luminos/apps" \
  "$STAGE/etc/aios"

if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip wheel
  .venv/bin/pip install -e ".[dev]"
fi

# Vendor pure-python deps + our packages into the deb
.venv/bin/pip install --upgrade --target "$STAGE/usr/lib/luminos-aios/site-packages" \
  aiohttp cbor2 pyyaml -q

cp -a libs/aios_common/aios_common "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/policy/aios_policy "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/dcpd/aios_dcpd "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/agentd/aios_agentd "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/ai_engined/aios_ai_engined "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/gateway/aios_gateway "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/rcpd/aios_rcpd "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/scheduler/aios_scheduler "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a services/store/aios_store "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a cli/aios_cli "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a sdk/python/aios "$STAGE/usr/lib/luminos-aios/site-packages/"
cp -a apps/control_center "$STAGE/usr/share/luminos/apps/"

write_wrapper() {
  local cmd="$1" mod="$2"
  cat >"$STAGE/usr/bin/$cmd" <<EOF
#!/bin/sh
export PYTHONPATH="/usr/lib/luminos-aios/site-packages\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m $mod "\$@"
EOF
  chmod 755 "$STAGE/usr/bin/$cmd"
}

write_wrapper aios-policy aios_policy.main
write_wrapper dcpd aios_dcpd.main
write_wrapper agentd aios_agentd.main
write_wrapper ai-engined aios_ai_engined.main
write_wrapper aios-gateway aios_gateway.main
write_wrapper rcpd aios_rcpd.main
write_wrapper aios-scheduler aios_scheduler.main
write_wrapper aios-store aios_store.main
write_wrapper aios aios_cli.main
write_wrapper rcp-dump aios_cli.rcp_dump

cat >"$STAGE/usr/bin/aios-control-center" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/luminos-aios/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec python3 /usr/share/luminos/apps/control_center/main.py "$@"
EOF
chmod 755 "$STAGE/usr/bin/aios-control-center"

cp -a systemd/system/*.service "$STAGE/lib/systemd/system/" 2>/dev/null || true
cp -a systemd/user/*.service "$STAGE/usr/lib/systemd/user/" 2>/dev/null || true
cp -a profiles/. "$STAGE/usr/share/luminos/profiles/" 2>/dev/null || true
cp -a fixtures/. "$STAGE/usr/share/luminos/fixtures/" 2>/dev/null || true
cp packaging/aios-default.yaml "$STAGE/etc/aios/policy.yaml"

SIZE=$(du -sk "$STAGE" | cut -f1)
cat >"$STAGE/DEBIAN/control" <<EOF
Package: luminos-aios
Version: ${VERSION}
Section: misc
Priority: optional
Architecture: ${ARCH}
Maintainer: luminOS Team <dev@luminos.local>
Depends: python3 (>= 3.10)
Recommends: python3-gi, python3-dbus, at-spi2-core
Installed-Size: ${SIZE}
Homepage: https://local/luminos
Description: luminOS AI OS core (DCP, Agent, Policy, RCP, Gateway)
 Session/system daemons and CLI for the luminOS desktop control plane.
EOF

cat >"$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

mkdir -p "$OUT"
dpkg-deb --build "$STAGE" "$OUT/${PKG}.deb"
echo "Built $OUT/${PKG}.deb"
dpkg-deb -I "$OUT/${PKG}.deb"
ls -lh "$OUT/${PKG}.deb"
