# luminOS 实现树（aios）

Debian 系派生发行版的自研用户态：DCP / Agent / Policy / AI Engine / RCP / Gateway。

构建决策见 [docs/BUILD_DECISION.md](docs/BUILD_DECISION.md)。

## 快速开始（开发机）

```bash
cd aios
make venv
make test          # 单测 + 集成（拉起完整守护进程栈）
make smoke         # CLI 冒烟
make run           # 前台运维：启动全部服务
aios ping
aios dcp targets
aios agent run --goal '在夹具里输入「你好」并点 OK'
aios-control-center   # http://127.0.0.1:8765 （需先 make run）
```

控制中心：

```bash
make run
.venv/bin/python apps/control_center/main.py --port 8765
```

## 日构

```bash
make daily-build
# 产物: dist/daily-YYYYMMDD/{*.deb,test.log,smoke.log,SUMMARY.md,...}
```

## 包与镜像

| 命令 | 产物 |
|------|------|
| `make deb` | `dist/luminos-aios_*.deb` |
| `make img-skeleton` | arm64 烧写镜像骨架 tar（rootfs 布局 + genimage 模板） |
| `live-build/` | Debian live ISO 配置（需 root + live-build 正式打 ISO） |

## 架构进程

| 进程 | 职责 |
|------|------|
| `aios-policy` | L0–L3 授权、确认、审计 |
| `dcpd` | 桌面操控平面（夹具 Mode-A / AT-SPI / Mode-C 降级） |
| `agentd` | 规划、工具总线、预算、急停 |
| `ai-engined` | 路由 / OCR 桩 / 注入防护 / BYO 登记 |
| `rcpd` | RCP 帧（Unix + TCP loopback） |
| `aios-gateway` | HTTP/MCP 能力总线 |
| `aios-scheduler` / `aios-store` | 调度与商店元数据 |

## 环境变量

| 变量 | 含义 |
|------|------|
| `AIOS_HEADLESS=1` | CI：L2 可自动确认，L3 仍需确认 |
| `AIOS_RUNTIME_DIR` | Unix socket 目录 |
| `AIOS_STATE_DIR` | 审计 / 技能 / 密钥句柄 |
| `AIOS_OFFLINE=1` | 强制本地模型路由 |
| `AIOS_RCP_LOOPBACK=1` | 打开 127.0.0.1:17420 |

## 版本

0.1.0 — M0 工程可日构基线（服务闭环 + deb + 镜像骨架 + live-build 配置）。
