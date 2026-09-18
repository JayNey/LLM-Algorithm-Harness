## Context

`SandboxExecutor` 在每个策略执行开始时创建，但可用性直到第一道题执行时才暴露；沙箱不可用时逐题抛错被策略捕获记为结果，harness 继续跑完全部题目。失败分类 `_derive_failure_category` 只检查迭代级 `sandbox_error`，未覆盖沙箱正常返回但逐用例标记 `sandbox_error` 的情况。

## Goals / Non-Goals

**Goals:**

- 任何模型调用之前完成一次沙箱探测，失败即中止并给出可行动提示。
- 用例级 `sandbox_error` 归类为 `system_error`。

**Non-Goals:**

- 不做沙箱自动修复（如自动启动 Docker、自动拉取镜像）。
- 不改变沙箱执行协议与资源限制语义。

## Decisions

1. **`SandboxExecutor.health_check()`。** 执行最小代码片段（`print`）走完整后端链路，成功返回 True；任何异常返回 False。预检与正式执行使用同一后端，探测结果即真实可用性。
2. **预检在每个策略的题目循环之前执行一次。** 放在 `_run_strategy` 创建沙箱之后、首题之前；失败抛 `RuntimeError`（含修复提示），由 CLI 捕获后 exit 1。不在策略间缓存结果——每次策略运行独立探测，保持各策略隔离语义。
3. **用例级 `sandbox_error` 并入迭代级判断。** `_derive_failure_category` 在检查迭代 `sandbox_error` 的同一层级检查 `final_result.test_results` 中是否存在 `sandbox_error` 用例，归类 `system_error`。

## Risks / Trade-offs

- [预检增加一次轻量代码执行] → 毫秒级，远低于一次模型调用成本。
- [预检通过但后续沙箱仍可能故障] → 预检只消灭"整批不可用"这一最大损耗场景；运行中故障仍由既有逐题记录兜底。
