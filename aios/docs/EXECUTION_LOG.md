# 执行记录: luminOS M0 工程落地（非 demo）

日期: 2026-09-30

## 步骤

| # | 操作 | 文件/命令 | 结果 |
|---|------|-----------|------|
| 1 | 阅读设计真源，冻结构建底座为 Debian 多架构 | `aios/docs/BUILD_DECISION.md` | ✅ |
| 2 | 建立 `aios/` 工程树与共享库（RCP/IPC/Policy） | `libs/aios_common/**` | ✅ |
| 3 | 实现守护进程栈 policy/dcpd/agentd/ai-engined/rcpd/gateway/scheduler/store | `services/**` | ✅ |
| 4 | CLI + Python SDK + TS RCP codec | `cli/` `sdk/` | ✅ |
| 5 | 控制中心（本机 HTTP 直连 RPC） | `apps/control_center/main.py` | ✅ |
| 6 | systemd unit、fixtures、profiles | `systemd/` `fixtures/` `profiles/` | ✅ |
| 7 | Widget Mirror GTK3 模块源码 + Makefile | `widget_mirror/gtk3/` | ✅（本机缺 libgtk-3-dev 未链出 .so） |
| 8 | deb 打包脚本产出真实 .deb | `packaging/build-deb.sh` → `dist/luminos-aios_0.1.0_amd64.deb` | ✅ 3.5MB |
| 9 | live-build 配置 + arm64 镜像骨架 | `live-build/` `scripts/mkimg/` | ✅ |
| 10 | 日构流水线 test→smoke→deb→img | `scripts/daily-build.sh` | ✅ 全 0 |
| 11 | 单测+集成 22 项、冒烟 PASS | `make test` `make smoke` | ✅ |

## 修改/新增清单（核心）

- `aios/libs/aios_common/` — 路径、错误码、RCP 编解码、Unix RPC、策略引擎与审计
- `aios/services/{policy,dcpd,agentd,ai_engined,rcpd,gateway,scheduler,store}/` — 可运行守护进程
- `aios/cli/` `aios/sdk/python/` `aios/sdk/ts/` — 操作入口与 SDK
- `aios/apps/control_center/` — 控制中心
- `aios/packaging/` `aios/systemd/` `aios/live-build/` `aios/scripts/` — 发行与日构
- `aios/docs/BUILD_DECISION.md` — 构建决策冻结
- 本文件与 `STEPS.md` `TEST_REPORT.md` `LESSONS.md`

## 日构产物

路径: `aios/dist/daily-20260930/`

- `luminos-aios_0.1.0_amd64.deb`
- `test.log` / `smoke.log` / `deb.log` / `img.log`
- `SUMMARY.md`（test=0 smoke=0 deb=0 img=0）
- `live-build-config/` 快照
- `generic-arm64-*.tar.gz` 镜像骨架
