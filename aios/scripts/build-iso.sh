#!/usr/bin/env bash
# Build luminOS live ISO — run on a machine WITH root + live-build.
# Usage: sudo ./scripts/build-iso.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ISO_OUT:-$ROOT/dist/iso}"
WORKDIR="${ISO_WORKDIR:-/var/tmp/luminos-live}"
DATE=$(date +%Y%m%d)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: need root. Example: sudo $0" >&2
  exit 1
fi

if ! command -v lb >/dev/null 2>&1; then
  echo "Installing live-build (Debian/Ubuntu)..."
  apt-get update
  apt-get install -y live-build debootstrap squashfs-tools xorriso isolinux syslinux-common
fi

# Ensure deb exists for includes
if [[ ! -f "$ROOT"/dist/luminos-aios_*.deb ]]; then
  echo "Building luminos-aios.deb as invoking user is root; use prebuilt if possible"
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    sudo -u "${SUDO_USER:-root}" bash -lc "cd '$ROOT' && bash packaging/build-deb.sh"
  else
    sudo -u "${SUDO_USER:-root}" bash -lc "cd '$ROOT' && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e '.[dev]' && bash packaging/build-deb.sh"
  fi
fi

DEB=$(ls -1 "$ROOT"/dist/luminos-aios_*.deb | head -1)
mkdir -p "$OUT" "$WORKDIR"
rm -rf "$WORKDIR"/*
mkdir -p "$WORKDIR"
cp -a "$ROOT/live-build/." "$WORKDIR/"
mkdir -p "$WORKDIR/config/packages.chroot" \
  "$WORKDIR/config/includes.chroot/etc/aios" \
  "$WORKDIR/config/hooks/live"

cp -a "$DEB" "$WORKDIR/config/packages.chroot/"
cp -a "$ROOT/packaging/aios-default.yaml" "$WORKDIR/config/includes.chroot/etc/aios/policy.yaml"

# Ensure executable hooks
chmod +x "$WORKDIR/auto/"* 2>/dev/null || true
chmod +x "$WORKDIR/hooks/"* 2>/dev/null || true
# live-build expects hooks under config/hooks/normal or live
if [[ -d "$WORKDIR/hooks" ]]; then
  cp -a "$WORKDIR/hooks/." "$WORKDIR/config/hooks/live/" 2>/dev/null || true
  for h in "$WORKDIR/config/hooks/live/"*; do
    [[ -f "$h" ]] || continue
    mv "$h" "${h}.chroot" 2>/dev/null || true
  done
fi

cd "$WORKDIR"
if [[ -x auto/config.sh ]]; then
  bash auto/config.sh
elif [[ -x auto/config ]]; then
  # auto/config may be a note file; prefer config.sh
  lb config --distribution bookworm --architectures amd64 --binary-images iso-hybrid
else
  lb config --distribution bookworm --architectures amd64 --binary-images iso-hybrid \
    --archive-areas "main contrib non-free non-free-firmware" \
    --debian-installer none \
    --bootappend-live "boot=live components locales=zh_CN.UTF-8 keyboard-layouts=cn hostname=luminos username=luminos"
fi

lb clean --purge || true
lb build 2>&1 | tee "$OUT/lb-build-$DATE.log"

mkdir -p "$OUT"
shopt -s nullglob
for iso in "$WORKDIR"/*.iso "$WORKDIR"/live-image-*.hybrid.iso; do
  [[ -f "$iso" ]] || continue
  dest="$OUT/luminos_${DATE}_amd64.iso"
  cp -a "$iso" "$dest"
  sha256sum "$dest" | tee "$OUT/SHA256SUMS"
  ls -lh "$dest"
  echo "ISO ready: $dest"
  exit 0
done

echo "ERROR: lb build finished but no ISO found in $WORKDIR" >&2
ls -la "$WORKDIR" | head -50 >&2
exit 1
