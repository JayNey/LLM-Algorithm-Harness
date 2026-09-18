# 验证报告：readable-console-logs

- 日期：2026-09-17
- 变更范围：`36e4df3` → HEAD（分支 `tweak/20260917/complete-failure-recording`，与 complete-failure-recording 同分支交付）
- 验证模式：full（delta spec `console-output`，4 项 Requirement / 5 个 Scenario）
- 关联：随 issue #13 交付分支一并提交（原 PR #28 已由用户撤回，两个 change 合并新建 PR）

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 3/3 勾选 |
| 2 | 实现符合 design.md 决策 | PASS | 双渲染器切换、第三方 logger 压制（含 openai 3.x 实际使用的 httpx2）、CLI 显式开关、脱敏前置 |
| 3 | Design Doc | N/A | tweak 预设无独立 Design Doc |
| 4 | 能力规格场景通过 | PASS | 映射见下 |
| 5 | proposal 目标满足 | PASS | 终端默认可读、JSON 显式保留、刷屏消除（实测） |
| 6 | delta spec 与 design 无矛盾 | PASS | 一致 |
| 7 | 关联文档可定位 | N/A | 同 3 |

## 规格场景 → 证据映射

- 控制台默认人类可读 → `test_console_format_renders_human_readable` + 演示实测输出（键值行、短时间戳）
- 机器格式显式可选 → `test_json_format_keeps_machine_readable`、`test_main_passes_log_format_to_setup_logging`
- 第三方噪音压制 → `test_third_party_noise_suppressed` + 演示实测（HTTP Request 行消失）
- 双格式脱敏一致 → `test_console_format_redacts_credentials`（JSON 路径由既有 #4 测试覆盖）

## 独立集成代码审查

- 结论 pass。已确认 `--log-format` 与既有 CLI 覆盖逻辑无冲突、脱敏顺序正确、管道场景无 ANSI。
- 发现与处置（1 medium + 3 low，均已修复并补测试）：
  1. medium「重复 setup_logging 时已绑定 logger 不切换格式」→ `cache_logger_on_first_use=False` + 注释修正，补 `test_repeat_setup_switches_format_for_bound_logger`。
  2. low「sys.stdout 为 None 时 isatty 崩溃」→ `bool(sys.stdout and sys.stdout.isatty())` 防护。
  3. low「log_file 混入 ANSI」→ 传入 log_file 时禁用颜色。
  4. low「fixture 清理不完整」→ 保存/恢复第三方级别 + `structlog.reset_defaults()`。

## 运行时检查

- Build：`comet check run build --local` exit=0（104aa601 日志）；Verify：exit=0，293 passed，覆盖率 95.28%（bd109a58 日志）
- 演示实测：默认 console 模式输出键值行、api_key 显示 [REDACTED]、HTTP Request 刷屏消失；`--log-format json` 保留旧行为
- OpenSpec 严格校验：valid

## 结论

检查项全部通过，审查问题闭环。验证通过。
