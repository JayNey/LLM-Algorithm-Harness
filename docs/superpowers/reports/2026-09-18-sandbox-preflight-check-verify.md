# 验证报告：sandbox-preflight-check

- 日期：2026-09-18
- 变更范围：`07159a9` → HEAD（分支 `tweak/20260918/sandbox-preflight-check`）
- 验证模式：full（delta spec `sandbox-preflight`，2 项 Requirement / 4 个 Scenario）
- 关联：源自当日三次评测因 Docker 沙箱不可用整批失败且逐题烧 token 的事故

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 5/5 勾选 |
| 2 | 实现符合 design.md 决策 | PASS | health_check 走真实 execute() 链路；预检在题目循环之前、任何 LLM 调用之前；用例级 sandbox_error/同族状态归类 system_error |
| 3 | Design Doc | N/A | tweak 预设无独立 Design Doc |
| 4 | 能力规格场景通过 | PASS | 映射见下 |
| 5 | proposal 目标满足 | PASS | 端到端负向实测：预检失败时零 API 调用、干净退出 |
| 6 | delta spec 与 design 无矛盾 | PASS | 一致 |
| 7 | 关联文档可定位 | N/A | 同 3 |

## 规格场景 → 证据映射

- 沙箱预检先于模型调用
  - 沙箱不可用时启动评测 → `test_run_strategy_preflight_failure_aborts_before_llm`（LLMClient 未创建、strategy.execute 未调用）+ 端到端实测：`docker_image=nonexistent/python:nope` + 假 key 运行 → 一行可行动错误 + 退出，无任何生成请求
  - 沙箱可用时正常执行 → 既有 harness 全流程测试 + `test_run_strategy_preflight_passes...`（mock 通过路径）
- 用例级沙箱故障归类
  - 用例级 sandbox_error → `test_sandbox_error_test_cases_classified_system_error`
  - 负向保护：全 wrong_answer 用例仍判 wrong_answer → `test_sandbox_error_test_cases...` 同族断言与上游 hidden 评测测试（18 个）全绿

## 独立集成代码审查

- 结论 pass：预检顺序正确（LLMClient 构造前）、子命令分发无误判回归、用例级映射不影响 hidden/feedback 语义
- 发现与处置（3 low + 1 info，已全部处置）：
  1. low「host 探针用 PATH 的 python3 与真实执行解释器不一致」→ health_check 改为委托真实 `execute()` 链路，一并消除
  2. low「docker 探针超时后容器可能残留」→ 委托真实 execute() 后由真实链路负责清理
  3. low「探针未复用真实运行的最小权限参数，保真度缺口」→ 同上，探针与真实运行同参数
  4. info「旧窄化 runtime/syntax 检查被宽检查覆盖，冗余」→ 已移除
- 回归保护：新增 5 个 health_check 专项测试（委托、失败、异常、双后端）

## 运行时检查

- Build：`comet check run build --local` exit=0（270e1b3f 日志）；Verify：exit=0，379 passed + 3 skipped，覆盖率 90.93%（f8532733 日志）
- OpenSpec 严格校验：valid
- 端到端负向实测：假 key + 不存在镜像 → `Sandbox preflight failed: ...` + stderr + exit 1，零 API 调用

## 结论

检查项全部通过，审查发现项全部修复（探针保真度重构）。验证通过。
