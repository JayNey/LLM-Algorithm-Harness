## 问题与根因

Evaluation.model 已持久化真实模型名，但 CostService._spend_rows 将其硬编码为 evaluation-run；cost_optimization_report 又仅以策略分组并输出同一占位名，导致不同模型的成本与准确率混合。

## 修复目标

成本拆分保留真实模型名，优化报告按模型和策略分别聚合；仅对 model 为 null 或空字符串的历史记录保留 evaluation-run 回退。保持现有 API、数据库 schema、计算公式、权限与时间过滤不变。

## 影响

仅修改 api/services/cost_service.py 与 tests/test_api_cost.py。修复现有模型维度语义，不新增 capability，不改变既有 spec 验收要求，无需 delta spec。

## 复现证据

命令：`pytest tests/test_api_cost.py -k 'preserves_saved_models or groups_by_saved_model' --no-cov -q`。修复前 2 failed：breakdown 返回 evaluation-run=1.44、gpt-4o-mini=0.4，丢失 other-model；优化报告仅有 2 个组合而非预期 5 个。首次测试夹具缺少 benchmark suite_id，补齐关联 suite 后得到上述业务断言失败。
