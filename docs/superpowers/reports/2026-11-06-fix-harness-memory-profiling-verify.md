# Harness 最终代码内存采样验证

变更 `fix-harness-memory-profiling` 对应 [#374](https://github.com/JayNey/LLM-Algorithm-Harness/issues/374)，验证对象为提交 `b9add824`。

## 完整性

OpenSpec 任务完成 1/1。`result-recording` 增量包含一条需求和三个场景，通过严格校验。

## 正确性

- 修复前，五个入口回归用例暴露沙箱采样未调用。关闭空间分析的用例通过。
- 修复后，真实 host 沙箱对公开用例测得至少 2 MiB 的 Python 分配峰值。序列化后的最终质量指标包含字节和 MiB 数值。
- 关闭空间分析时不调用采样方法。导入受限、Docker 不可用和没有公开用例时，结果保留空峰值和不可用说明，判题状态保持原值。
- 多轮反馈只采样最终代码。逐轮空间指标未采样，各轮仍可使用同一组静态维度比较。
- Harness、演化、质量分析和沙箱相关测试通过 203 项，跳过 8 项。Black、Ruff、Git diff 检查和 Python wheel 构建通过。

## 一致性

最终分析使用当前策略沙箱及题目上下文，沿用沙箱已有的公开用例、输出校验和执行限制。实现与本变更的精简设计一致。Tweak 的 `review_mode: off` 跳过独立自动代码审查。

## 类型检查基线

Mypy 在 `api/progress.py`、`api/services/cost_alert_service.py` 和 `api/files/parsing.py` 报告 4 项错误。以主线 `2d0a3f92` 的 Harness 源码作为 Mypy shadow file 复跑，错误集合完全相同。

## 离线全量验证

使用符合仓库依赖约束的 Anthropic 0.125.0，并允许测试绑定本机回环端口。运行 `python3 -m pytest -m 'not online' -q`，4,042 项通过、18 项跳过，总覆盖率 93.37%，`src` 覆盖率 92.40%。Harness 的峰值采样回归使用真实 host 沙箱，Docker 不可用场景使用受控替身。

## 归档校验

Comet 归档通过 6 项检查。增量已并入 `result-recording` 主规范，合并后的规范通过严格校验。交付方式为提交归档、推送绑定分支并创建 PR。
