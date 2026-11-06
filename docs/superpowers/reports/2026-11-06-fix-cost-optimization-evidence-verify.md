# 成本优化结果与费用验证

变更 `fix-cost-optimization-evidence`，实现提交 `a60d6fa`，对应 [GitHub Issue #363](https://github.com/JayNey/LLM-Algorithm-Harness/issues/363)。

## 结论

通过。OpenSpec 任务 1/1 完成，两项增量需求均有实现和测试证据。验证按 tweak 的精简 `design.md` 执行，流程配置的 `review_mode: off` 跳过独立自动审查。

## 验收场景

- HTTP 回归捕获传给建议引擎的真实组合并继续调用该引擎。一题两策略全部失败时通过数为 0，准确率为 0。仅一项通过时，分母为 2，准确率为 0.5。覆盖部分结果和仅存进度的记录，并核对排名及三项建议。实现位于 `api/services/cost_service.py:68` 和 `api/services/cost_service.py:762`。
- 基准执行器保留定价完整性，正金额小计、缺失金额及缺少标记的历史数据均有 HTTP 排除测试。完整零费用显示为 0，未知费用为 null。正费用的基准使用实际通过数计算性价比。见 `src/benchmark/executor.py:153` 和 `src/cost_optimizer.py:34`。
- 现有排名测试验证按性价比降序、未知费用排除和推荐目标。真实基准与评估的费用聚合仍在当前用户范围内。

## 执行证据

- 修复前在临时 SQLite 复现通过数 2、准确率 2.0 和费用已知。12 项新增或更新的回归断言在旧实现上失败。
- 最终实现的成本 API、建议引擎、基准与任务回归通过 180 项。Python wheel 构建、编译、Ruff、Black、编码检查、Git 空白检查和 OpenSpec 严格校验通过。
- 全量非在线套件在最后一次类型和求和整理前运行，3960 项通过、18 项跳过，4 项 Anthropic 参数用例因本机安装了 1.5.0 而在初始化时失败。未修改的主线可复现相同错误。临时采用项目约束内的 Anthropic 0.125.0 单独复跑该文件，12 项全部通过。最终实现另有上述 180 项定向结果。
- CI 类型检查在本机环境报告 4 条错误。对主线归档运行相同命令，输出逐行相同，涉及 `api/files/parsing.py`、`api/progress.py` 和 `api/services/cost_alert_service.py`。
