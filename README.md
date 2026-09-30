# luminOS

基于 Linux、**面向 AI Agent** 的操作系统。设计真源与可日构实现分列如下。

## 文档

- [luminOS完整设计方案.md](./luminOS完整设计方案.md) — 唯一正式设计真源（v1.4）
- [aios/docs/BUILD_DECISION.md](./aios/docs/BUILD_DECISION.md) — 构建底座冻结（Debian 多架构，非 Yocto）
- [aios/docs/EXECUTION_LOG.md](./aios/docs/EXECUTION_LOG.md) / [STEPS.md](./aios/docs/STEPS.md) / [TEST_REPORT.md](./aios/docs/TEST_REPORT.md) / [LESSONS.md](./aios/docs/LESSONS.md)

## 仓库

https://github.com/yanggan2015/AIOS-Design

## 实现（aios/）

M0 可日构工程在 [`aios/`](./aios/README.md)：

```bash
git clone https://github.com/yanggan2015/AIOS-Design.git
cd AIOS-Design/aios
make venv && make test && make smoke && make daily-build
```

已实现并验证：

- 守护进程：`aios-policy` `dcpd` `agentd` `ai-engined` `rcpd` `aios-gateway` `aios-scheduler` `aios-store`
- CLI / Python SDK / TS RCP codec / 控制中心
- 真实 `.deb`、本地 APT 仓布局、live-build 配置、arm64 烧写镜像骨架
- `make daily-build` 全绿（test/smoke/deb/img）

### 换有权限的机器打 ISO

见 [`aios/docs/ISO_BUILD_ON_BUILDER.md`](./aios/docs/ISO_BUILD_ON_BUILDER.md)：

```bash
cd AIOS-Design/aios
make venv && make deb
sudo make iso    # → dist/iso/luminos_YYYYMMDD_amd64.iso
```

## 许可

设计与实现以仓库声明为准；若未另行说明，保留所有权利。
