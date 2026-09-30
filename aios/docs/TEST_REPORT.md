# 测试报告: luminOS M0

## 测试环境

- 主机: Linux 6.8 / Ubuntu 22.04 用户态
- Python: 3.10.12 + 项目 venv
- 日期: 2026-09-30
- 模式: `AIOS_HEADLESS=1`（无图形会话，使用 fixture 通道）

## 测试项

| 测试项 | 预期 | 实际 | 结论 |
|--------|------|------|------|
| RCP 编解码往返 / 坏 CRC / 重同步 | 单测通过 | 15 unit passed | ✅ |
| Policy L0 放行 / L3 需确认 / 密码控件 DENY | 符合设计 6.1 | 通过 | ✅ |
| Fixture DCP 输入+点击副作用 | label=`OK:<text>` | 通过 | ✅ |
| 八进程 ping | 全 ok | 通过 | ✅ |
| Hello DCP E2E | 快照文本正确 | 通过 | ✅ |
| Agent 自然语言目标 | status=done | 通过 | ✅ |
| power.reboot 未确认 | NEED_CONFIRM | 通过 | ✅ |
| RCP 配对 + WIN_LIST | 含 fixture:hello | 通过 | ✅ |
| 提示注入防护 | blocked=true | 通过 | ✅ |
| Gateway MCP tools/call | 200 + result | 通过 | ✅ |
| CLI smoke | `[smoke] PASS` | 通过 | ✅ |
| `dpkg-deb` 产物 | 可 `dpkg-deb -I` | luminos-aios_0.1.0_amd64.deb 3.5M | ✅ |
| 日构流水线 | 全 RC=0 | daily-20260930 SUMMARY 全 0 | ✅ |

## 性能数据（本机 headless）

| 场景 | 观测 |
|------|------|
| `make test` 墙钟 | ~1.5–2s |
| `scripts/run-stack.sh` 就绪 | ~1s 内八服务 socket 就绪 |
| Agent「输入+点 OK」 | <100ms（规则规划，无大模型） |

## 未在本机执行（环境限制）

| 项 | 原因 |
|----|------|
| 真实 AT-SPI 点击 GTK 窗口 | CI/无桌面会话；代码路径已接 Atspi 列举 |
| `libaios-mirror.so` 链接 | 未装 `libgtk-3-dev`（无 sudo） |
| `lb build` 正式 ISO | 需 root + live-build + 较长时间 |
| 板级可启动 `.img` | 需 debootstrap/root + 厂商 BSP |

以上不影响 M0「可日构用户态 + deb + 配置冻结」验收。
