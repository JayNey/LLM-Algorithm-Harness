# 自定义定价验证报告

结论：PASS。Change：custom-pricing；工作分支：comet/custom-pricing；实现提交：7f4cc54、513ba76。验证日期：2026-10-26。

## 完整性

两项 tasks 均已完成。对应既有 cost-estimation/custom-pricing 能力的新增验收要求已实现，没有新增数据库结构、HTTP 端点或前端改动。本次涉及四个源码文件、一个既有测试文件；其余变更为 Comet/OpenSpec 元数据和产物。工作区剩余未提交变更均属于本次验证报告和流程状态。

## 正确性与场景证据

- 最新版本参与成本和预算：test_web_pricing_drives_real_cost_and_budget 使用真实 CostService 保存两个版本，并经过真实上下文解析、策略、provider 响应处理、trace、成本估算和 TaskService 结算。每千输入/输出 tokens 均为 $0.1 时，一次调用累计 $0.2，超过 $0.15 后在单元边界暂停。
- 恢复刷新：同一测试在暂停后保存 $0.02 新价格并调整上限，恢复只执行剩余题目，总成本 $0.24；已经结算的 $0.2 不重算。
- 零价：同一参数化测试验证零价被标记为已知成本，并且评估正常完成。
- 快照与回退：test_web_pricing_snapshot_shared_by_all_and_late_runtimes 覆盖两个初始策略和临时构造的 runtime。数据库更新不影响已加载快照，重新解析则刷新；精确覆盖优先于文件，文件前缀、内置和未知回退保留。
- 缓存与未知用量：test_web_pricing_reprices_cache_without_changing_history 对 OpenAI/Anthropic 和已知/未知用量进行参数化验证，覆盖当前价格、override 来源、provider 模型身份、未知成本及历史缓存对象不变。
- 服务商别名：真实执行集成中配置 test-model、provider 返回 provider-canonical-model，仍按配置模型覆盖计费；缓存元数据保持 provider 模型名。
- 既有预算作用域与 Web 成本 API、报告历史价格等通过相关回归测试验证。

## 验证命令

- `pytest tests/test_celery_tasks.py tests/test_pricing.py tests/test_llm_client.py tests/test_cost_strategy.py tests/test_api_cost.py tests/test_cost_estimation.py tests/test_cost_alert.py --no-cov -q`：217 passed，5 项既有 Pydantic 弃用警告。此为定向回归，未声明全仓测试或覆盖率达标。
- `black --check src/utils/pricing.py src/tasks/evaluation.py src/harness.py src/llm_client.py tests/test_celery_tasks.py`：通过。
- `ruff check src/utils/pricing.py src/tasks/evaluation.py src/harness.py src/llm_client.py tests/test_celery_tasks.py`：通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/custom-pricing-dist`：成功构建 llm_algorithm_harness-0.1.0-py3-none-any.whl。
- `comet classic openspec -- validate custom-pricing --strict`：有效。
- `git diff --check`：通过。

## 设计一致性与独立审查

实现符合 change design.md：共享业务数据库、每执行快照、精确模型覆盖、缓存复制重计价、保留历史结算。Tweak 未生成完整 Superpowers Design Doc/plan，因此相关完整流程检查不适用；没有设计漂移。

已按 requesting-code-review 派发独立只读审查。唯一 P2 问题是缓存重计价改变 pricing_metadata.model，影响 models_used 的归属；已补失败断言复现并于 513ba76 修复，最终 217 项回归通过。审查未发现其他明确的正确性、安全或边界问题。没有未解决的 CRITICAL/IMPORTANT 问题或待接受偏差。

## 边界

价格作用域沿用当前 Web 全局目录。价格在启动/恢复时读取，在途评估使用已有快照；预算沿用单元边界控制。Provider、Docker 和外部服务均由测试替身隔离，未进行真实付费 API 调用。

## 归档与交付选择

用户明确选择 C：归档、提交、推送 comet/custom-pricing 并创建面向 main 的 PR。归档已按 OpenSpec delta 语义同步主规格并移动至 openspec/changes/archive/2026-10-26-custom-pricing；归档完整性守卫通过。归档提交后的远端操作由本次选择授权，不进行分支合并或删除。
