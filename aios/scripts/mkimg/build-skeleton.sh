#!/usr/bin/env bash
# Build a flashable image *skeleton* for embedded (arm64 layout).
# Full rootfs populate needs debootstrap/root; this always produces a
# reproducible partition map + rootfs staging tree for daily builds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${OUT_DIR:-$ROOT/dist/img-skeleton}"
BOARD="${BOARD:-generic-arm64}"
DATE=$(date +%Y%m%d)
STAGE="$OUT/$BOARD-$DATE"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{boot,rootfs/usr/share/luminos,rootfs/etc/aios,meta,bsp}

cat >"$STAGE/meta/image.yaml" <<EOF
board: $BOARD
arch: arm64
date: $DATE
scheme: luminOS-embedded-v1
partitions:
  - name: boot
    fstype: vfat
    size_mb: 256
  - name: root
    fstype: ext4
    size_mb: 4096
userspace: debian-bookworm-arm64
aios_packages:
  - luminos-aios
notes: |
  Populate rootfs with: debootstrap --arch=arm64 bookworm rootfs http://deb.debian.org/debian
  then install luminos-aios_*.deb from APT repo / dist/.
  Board-specific U-Boot/kernel go in bsp/ (not generated here).
EOF

cat >"$STAGE/bsp/README.md" <<EOF
# BSP drop-in for $BOARD

Place:
- \`u-boot.bin\` / \`idbloader.img\` / \`u-boot.itb\` (vendor dependent)
- \`Image\` or \`vmlinuz\`
- \`*.dtb\`
- flash layout notes

Yocto/vendor SDK may produce these binaries; luminOS userspace stays Debian.
EOF

# Stage aios config + profiles into future rootfs
cp -a "$ROOT/packaging/aios-default.yaml" "$STAGE/rootfs/etc/aios/policy.yaml"
cp -a "$ROOT/profiles/." "$STAGE/rootfs/usr/share/luminos/profiles/" 2>/dev/null || mkdir -p "$STAGE/rootfs/usr/share/luminos/profiles"
cp -a "$ROOT/fixtures/." "$STAGE/rootfs/usr/share/luminos/fixtures/" 2>/dev/null || true

# genimage.cfg template
cat >"$STAGE/meta/genimage.cfg" <<'EOF'
image boot.vfat {
  vfat { label = "BOOT" }
  size = 256M
}
image rootfs.ext4 {
  ext4 { label = "ROOT" }
  size = 4G
}
image luminos.img {
  hdimage {}
  partition boot {
    partition-type = 0xC
    bootable = "true"
    image = "boot.vfat"
  }
  partition root {
    partition-type = 0x83
    image = "rootfs.ext4"
  }
}
EOF

# Placeholder sparse image header (real dd image needs root + genimage)
dd if=/dev/zero of="$STAGE/meta/luminos-${BOARD}-PLACEHOLDER.img" bs=1M count=8 status=none
sha256sum "$STAGE/meta/luminos-${BOARD}-PLACEHOLDER.img" >"$STAGE/meta/SHA256SUMS"
tar -C "$OUT" -czf "$OUT/${BOARD}-${DATE}.tar.gz" "$(basename "$STAGE")"
echo "img skeleton: $OUT/${BOARD}-${DATE}.tar.gz"
ls -lh "$OUT/${BOARD}-${DATE}.tar.gz"
