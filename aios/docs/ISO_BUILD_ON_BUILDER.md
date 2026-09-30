# 换机打 ISO / 嵌入式镜像操作手册

在**有 sudo 权限**的 Debian/Ubuntu 构建机上执行。开发机无 root 时只推代码；ISO 在本手册完成。

仓库: https://github.com/yanggan2015/AIOS-Design

## 0. 拉代码

```bash
git clone https://github.com/yanggan2015/AIOS-Design.git
cd AIOS-Design/aios
```

或已有仓库：

```bash
cd AIOS-Design
git pull origin main
cd aios
```

## 1. 先验证用户态（不需要 root）

```bash
make venv
make test
make smoke
make deb
```

预期：测试全绿；`dist/luminos-aios_0.1.0_*.deb` 存在。

## 2. 打 live ISO（需要 root）

```bash
sudo ./scripts/build-iso.sh
```

产物：

- `dist/iso/luminos_YYYYMMDD_amd64.iso`
- `dist/iso/SHA256SUMS`
- 构建日志 `dist/iso/lb-build-*.log`

依赖：`live-build`、`debootstrap`、`squashfs-tools`、`xorriso`（脚本会尝试 `apt-get install`）。

耗时与磁盘：建议 ≥20GB 空闲；首次 bootstrap 视网速 20–90 分钟。

## 3. 嵌入式可启动镜像（需要 root + arm64 工具）

骨架（无需 root，日构已有）：

```bash
make img-skeleton
```

完整 rootfs（示例，bookworm arm64）：

```bash
sudo apt-get install -y debootstrap qemu-user-static binfmt-support genimage
sudo debootstrap --arch=arm64 bookworm /var/tmp/luminos-arm64-root http://deb.debian.org/debian
sudo cp dist/luminos-aios_*.deb /var/tmp/luminos-arm64-root/tmp/
sudo chroot /var/tmp/luminos-arm64-root bash -c 'apt-get update && apt-get install -y python3 && dpkg -i /tmp/luminos-aios_*.deb || apt-get -f install -y'
# 再按 bsp/<board>/ 放入 U-Boot/内核/DTB，用 genimage 出 .img
```

板级 BSP 不进主仓时，放到 `bsp/<board>/` 后日构扩展。

## 4. Widget Mirror（需要 libgtk-3-dev）

```bash
sudo apt-get install -y libgtk-3-dev pkg-config
cd widget_mirror/gtk3 && make && sudo make install
```

## 5. 回传产物（可选）

```bash
# 不要把巨大 ISO 强行塞进 git；用 Release / 对象存储
gh release create luminos-$DATE dist/iso/*.iso dist/luminos-aios_*.deb --title "luminOS $DATE"
```

## 构建决策提醒

见 `docs/BUILD_DECISION.md`：用户态 Debian 多架构；Yocto 仅板级 BSP。
