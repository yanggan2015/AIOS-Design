# 经验总结: luminOS M0 落地

## 遇到的问题 & 解决方案

1. **问题**: 误以为可能用 Yocto 做主工程 → **解决**: 按设计真源冻结为 Debian 多架构用户态；Yocto/厂商 SDK 只做板级 BSP。写入 `BUILD_DECISION.md`。
2. **问题**: 集成测试里服务起来了但 client 连不上 socket → **解决**: pytest 父进程也必须 `os.environ` 设置同一 `AIOS_RUNTIME_DIR`，不能只传给子进程。
3. **问题**: CRC 单测写死了错误期望值 → **解决**: 与 `zlib.crc32` 对齐，不手写 magic 常数。
4. **问题**: 无 sudo 无法装 `libgtk-3-dev` → **解决**: Widget Mirror Makefile 缺依赖时 SKIP，不阻断日构；源码与安装路径仍完整保留。
5. **问题**: `pip install --user` 权限失败 → **解决**: 项目内 `.venv` 作为唯一开发/CI 环境。
6. **问题**: 把「夹具通道」当成 demo 会与「真系统」混淆 → **解决**: 夹具是无图形会话下的一等认证通道（设计 H10）；有显示时叠加 AT-SPI / Mirror / Mode-C，策略与 RCP 路径不变。

## 关键发现

- 八个守护进程用 Unix JSON-RPC 总线足够支撑 M0 日构与 CLI/SDK/控制中心；D-Bus 可后续加桌面集成，不必阻塞闭环。
- RCP 先 Unix + TCP loopback，比一上来 TLS/串口更能保证编解码与鉴权单测稳定。
- `AIOS_HEADLESS` 下 L2 可自动确认、L3 仍拦截，能在无 UI 确认框时跑 CI，又不会把 reboot 测成放行。

## 改进建议（下一迭代，非阻塞）

1. 在有桌面的机器上补 GTK 夹具 + AT-SPI 动作绑定与 Widget Mirror `.so` 链接进 deb。
2. builder 容器（root）跑 `lb build` 与 `debootstrap --arch=arm64`，把 ISO/可启动 img 纳入日构可选 stage。
3. `bsp/<board>/` 接入第一块认证板（建议 RK 系你侧已有资料的型号）。
4. ai-engined 接入真实本地后端（llama.cpp/ORT）作为可选插件，默认仍保持 rules 以保证离线日构确定性。
5. 审计日志查询 CLI、控制中心确认弹窗（非 headless）。

## 避免重复试错（清单）

- 不要把主工程迁去 Yocto「为了能烧板」。
- 不要在无 `AIOS_RUNTIME_DIR` 对齐的情况下写集成测试。
- 不要在 CI 默认放行 L3。
- 不要把 API Key 写进日志（BYO 只存 handle）。
- 不要用 Snap 当默认应用格式（设计明确不做）。
