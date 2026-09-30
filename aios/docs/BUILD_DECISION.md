# luminOS 构建与发行决策（冻结）

| 项 | 决定 |
|---|---|
| 日期 | 2026-09-30 |
| 修订 | 2026-09-30：明确 **x86 + 嵌入式板卡** 双交付 |
| 状态 | **已冻结，禁止无评审地改换用户态底座** |
| 产品形态 | 同一套 AI/DCP/Agent 用户态；按 SKU 出不同启动镜像 |

## 结论（三句话）

1. **用户态底座统一为 Debian 系多架构（先 `amd64` + `arm64`）+ 自研 deb 栈。**  
2. **交付分两路：x86 走 live ISO/安装器；嵌入式走可烧写磁盘镜像（同 rootfs 谱系）。**  
3. **Yocto/厂商 SDK 只允许做板级 BSP（U-Boot/厂商内核/设备树），不取代 APT 用户态。**

「能烧到板子上」≠「整盘用 Yocto 做 OS」。板卡要的是 boot 链 + 根文件系统；AI 操作系统能力仍在 deb 用户态。

## 目标矩阵

| SKU | 硬件 | 日构主产物 | 写入方式 |
|---|---|---|---|
| **PC** | x86_64 | `luminos_<date>_amd64.iso` | U 盘安装 / Calamares |
| **SBC / 工控板** | aarch64（如 RK3588 等认证板） | `luminos_<date>_<board>.img.xz` | `dd` / 厂商烧录工具 |
| **（可选）弱资源设备** | 无完整桌面 | 另立产品线，不叫完整 luminOS 桌面 | 可 Yocto；只共享协议库 |

M0 先打通：**amd64 ISO** + **一条 arm64 通用 rootfs/镜像骨架**；具体 board 适配按硬件矩阵逐块加。

## 为什么用户态仍不是 Yocto

设计承诺（deb/Flatpak/APT、DCP、AT-SPI、商店）在 x86 和嵌入式桌面板上都成立。  
若嵌入式也要「Agent 操控桌面应用」，板子上跑的仍是完整桌面用户态——用 Debian `arm64` 比整盘 Yocto 更贴设计。

Yocto 适合：只做 U-Boot、厂商内核、DTB、GPU 闭源 blob 的 **BSP 层**。

## 架构分层（双交付共享）

```
                    ┌─────────────────────────────────┐
                    │  aios 自研包（同一套源码打 deb）   │
                    │  dcpd / agentd / policy / rcpd…   │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │  Debian 用户态（amd64 / arm64）   │
                    │  APT + Flatpak + Wayland 栈      │
                    └───────────────┬─────────────────┘
                         ┌──────────┴──────────┐
                         ▼                     ▼
              ┌──────────────────┐   ┌─────────────────────┐
              │ PC 交付           │   │ 嵌入式交付            │
              │ live-build → ISO  │   │ rootfs + BSP → .img  │
              │ grub / uki        │   │ U-Boot + 厂商/LTS 核  │
              └──────────────────┘   └─────────────────────┘
```

| 层 | 谁负责 | 说明 |
|---|---|---|
| 自研 AI/DCP/Agent/RCP | `aios/` → **多架构 deb** | 一套源码，`amd64`/`arm64` 各编一份 |
| 通用用户态 | Debian Bookworm 派生 | 包集合按 profile：`pc` / `embedded-desktop` |
| PC 启动与安装 | live-build + Calamares | 设计 A2 |
| 板卡启动 | `bsp/<board>/`：U-Boot、内核、DTB、烧录布局 | 可来自厂商 SDK **或** 该板的 Yocto BSP 仅导出 boot 部件 |
| 板卡根文件系统 | 同一 APT 仓的 arm64 包组装（`debos` / `genimage` / 自研 `scripts/mkimg`） | **不是** 另写一套 Yocto recipe 重做桌面 |

## 日构流水线

```
日构
  ├─ 1. 源码 aios/  →  deb（amd64 + arm64，可交叉或容器内原生）
  ├─ 2. 内部 APT 仓 →  reprepro/aptly（多 arch）
  ├─ 3a. live-build →  luminos_*_amd64.iso
  ├─ 3b. mkimg      →  luminos_*_<board>.img  （rootfs⊂同一仓 + bsp/<board>）
  ├─ 4. 冒烟        →  QEMU amd64 + QEMU aarch64（无板也可日构）
  └─ 5. 产物索引    →  SHA256SUMS + TEST_REPORT
```

## 嵌入式约束（必须提前认清）

1. **完整 luminOS 桌面**（DCP/AT-SPI/Agent）需要内存/存储预算；认证板给出最低线（建议 ≥4GB RAM、≥16GB eMMC，可按实测改）。
2. 厂商闭源 GPU/NPU：进 `bsp/<board>` 与硬件矩阵，不进通用 deb 的「假装支持」。
3. 无图形会话时：`rcpd`/`SYS_*` 仍可用；`DCP_*` 返回 `NO_SESSION`（设计已有）。
4. 若某板只能跑 Buildroot 级根且装不下桌面——标成 **网关/无头 SKU**，不承诺 Mode-A 桌面操控。

## 明确不做

1. 不用 Yocto 重做整套 luminOS 桌面用户态。  
2. 不用「只维护 x86、嵌入式以后再说」——日构从 M0 起就要有 **多 arch 包** 与 **镜像骨架**。  
3. 不把每个板的 BSP 细节揉进 `aios` 主包；BSP 隔离在 `bsp/<board>/`。  
4. 不承诺任意板卡即插即用——只认硬件矩阵内 SKU。

## 仓库落点（相对 `aios/`）

```text
packaging/debian/     # deb 打包
live-build/           # PC ISO
scripts/mkimg/        # 嵌入式镜像组装
bsp/                  # 每板 boot/内核/分区表（可 submodule）
docs/BUILD_DECISION.md
```

## 修订规则

变更用户态底座（例如整盘改 Yocto）须同时改设计真源并记入 `LESSONS.md`。  
仅新增 `bsp/<board>` 或 arch 不视为改换底座。
