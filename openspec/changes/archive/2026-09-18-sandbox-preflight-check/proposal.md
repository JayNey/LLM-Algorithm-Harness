## Why

今天三次评测因为 Docker 沙箱不可用而整批失败：harness 明知沙箱不可用仍把全部题目跑完，逐题消耗 API token（一次 12 题约 3 万 token 打水漂）；同时用例级 `sandbox_error` 被失败分类误判为 `wrong_answer`，掩盖了真实原因。

## What Changes

- 新增沙箱预检（preflight）：每个策略开始执行前，先用一次最小代码执行探测沙箱可用性；不可用时立即以清晰的错误中止运行，**在任何模型 API 调用之前**。
- CLI 捕获预检错误并以 exit 1 输出可行动的修复提示（启动 Docker Desktop / 确认镜像）。
- 失败分类修复：用例级 `sandbox_error`（沙箱返回的逐用例失败）与迭代级沙箱异常同等对待，归类为 `system_error` 而非 `wrong_answer`。

## Capabilities

### New Capabilities

- `sandbox-preflight`: 定义评测前的沙箱可用性预检行为与失败分类边界。

## Impact

- 影响 `src/sandbox_executor.py`、`src/harness.py`、`src/strategy_base.py`、`src/main.py`。
- 不改变沙箱执行协议、判题语义与既有失败分类的其他取值。
