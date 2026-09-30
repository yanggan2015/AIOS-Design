# 手动执行步骤: luminOS M0 日构与运行

## 前置条件

- Linux（已在 Ubuntu 22.04 验证）
- `python3 >= 3.10`、`dpkg-deb`、可选 `libgtk-3-dev`（Widget Mirror）
- 打完整 ISO 另需: `live-build`、root、网络访问 Debian mirror
- 嵌入式完整 `.img` 另需: `debootstrap`（arm64）、板级 BSP 二进制、root

## Step 1: 安装开发环境

```bash
cd /path/to/AIOS-Design/aios
make venv
```

预期: `.venv/` 存在，`aios` `dcpd` 等入口在 `.venv/bin/`。

## Step 2: 跑测试

```bash
make test
```

预期: `22 passed`（15 unit + 7 integration）。

## Step 3: 冒烟

```bash
make smoke
```

预期: 输出 `[smoke] PASS`。

## Step 4: 启动服务栈并操作

```bash
make run
aios ping
aios dcp targets
aios agent run --goal '在夹具里输入「你好」并点 OK'
python3 apps/control_center/main.py --port 8765
# 浏览器打开 http://127.0.0.1:8765
```

停止:

```bash
make stop
```

## Step 5: 打 deb 与 APT 仓

```bash
make deb
bash scripts/make-apt-repo.sh
ls -lh dist/luminos-aios_*.deb
```

预期: 生成约 3.5MB 的 `luminos-aios_0.1.0_*.deb` 与 `dist/apt-repo/`。

## Step 6: 日构

```bash
make daily-build
cat dist/daily-$(date +%Y%m%d)/SUMMARY.md
```

预期: SUMMARY 中 test/smoke/deb/img 均为 0。

## Step 7: 嵌入式镜像骨架

```bash
make img-skeleton
# 或 BOARD=rk3588 make img-skeleton  （先扩展 bsp/rk3588）
```

预期: `dist/img-skeleton/generic-arm64-YYYYMMDD.tar.gz`。

## Step 8:（可选）Widget Mirror

```bash
sudo apt install libgtk-3-dev
cd widget_mirror/gtk3 && make
# GTK_MODULES=aios-mirror 指向模块目录后启动 fixtures/gtk_hello/app.py
```

## Step 9:（需 root）正式 live ISO

```bash
cd live-build
sudo bash auto/config.sh
sudo lb build
```

预期: 产出 hybrid ISO（取决于 builder 环境；日构默认只冻结配置不强制打 ISO）。
