#!/usr/bin/env bash
# Initialize a local APT repo layout and include built luminos-aios deb.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${REPO_DIR:-$ROOT/dist/apt-repo}"
CODENAME="${CODENAME:-bookworm}"
ARCH="${ARCH:-amd64}"
mkdir -p "$REPO/pool/main" "$REPO/dists/$CODENAME/main/binary-$ARCH"
DEB=$(ls -1 "$ROOT"/dist/luminos-aios_*.deb 2>/dev/null | head -1 || true)
if [[ -z "$DEB" ]]; then
  bash "$ROOT/packaging/build-deb.sh"
  DEB=$(ls -1 "$ROOT"/dist/luminos-aios_*.deb | head -1)
fi
cp -a "$DEB" "$REPO/pool/main/"
cd "$REPO"
PKG_FILE="dists/$CODENAME/main/binary-$ARCH/Packages"
if command -v dpkg-scanpackages >/dev/null 2>&1; then
  dpkg-scanpackages -m pool /dev/null >"$PKG_FILE"
else
  {
    echo "Package: luminos-aios"
    echo "Version: 0.1.0"
    echo "Architecture: $ARCH"
    echo "Maintainer: luminOS Team <dev@luminos.local>"
    echo "Filename: pool/main/$(basename "$DEB")"
    echo "Size: $(stat -c%s "pool/main/$(basename "$DEB")")"
    echo "SHA256: $(sha256sum "pool/main/$(basename "$DEB")" | awk '{print $1}')"
    echo "Description: luminOS AI OS core"
    echo
  } >"$PKG_FILE"
fi
gzip -9cf "$PKG_FILE" >"${PKG_FILE}.gz"
cat >"$REPO/README.md" <<EOF
# luminOS local APT repo

\`\`\`bash
echo 'deb [trusted=yes] file:$REPO $CODENAME main' | sudo tee /etc/apt/sources.list.d/luminos.list
sudo apt update
sudo apt install luminos-aios
\`\`\`
EOF
echo "APT repo at $REPO"
ls -la "$REPO/pool/main"
