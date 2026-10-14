## Why

评估任务已能通过 Celery 异步启动并可靠入队（#149 / #181 / #182），但 `src/tasks/evaluation.py` 的 `run_evaluation_task` 仍用占位 mock `worker()` 直接返回 `{"success": True, "mock": True}` —— 评估从不真正调用 LLM、不执行沙箱、不产生成本、不写入 `EvaluationResult`。对用户而言「评估」目前是一个只把单元标记为假成功的空壳。本次补齐真实执行体，让评估名副其实，闭合 issue #149 拆分出的 ① 项。

## What Changes

- 用真实执行替换 `run_evaluation_task` 中的 mock `worker()`：按 (strategy × problem) 单元驱动 `AlgorithmHarness` 执行链，完成 LLM 调用与沙箱执行。
- 从业务库问题存储（`ProblemStore.get_by_problem_id`）把 `Evaluation.problem_ids` 解析为 `Problem`；题目缺失时按明确的单元失败处理并记录原因，不静默跳过。
- 通过 `auth.llm_config(api_key_id, owner_id, model)` 解析真实 LLM 凭证与供应商。
- **BREAKING**：新增 `model` 字段 —— `EvaluationCreateRequest` 增加必填 `model`，`evaluations` 表增加 `model` 列（含 Alembic 迁移）。当前评估没有任何模型输入，而 `llm_config` 必须传 model，真实执行无法在不补齐该字段的情况下进行。
- 逐单元写入 `EvaluationResult`（`status` / `metrics` / `error_message`），并聚合更新 `Evaluation.spent_usd` / `completed_count` / `failed_count`。
- 接入成本统计：单元执行后累计 `spent_usd`；达到 `budget_cap_usd` 时按既有 `paused` 语义停止调度后续单元，保留已完成结果。
- 保持既有 Celery 生命周期、状态机、入队时序，以及 `start` / `pause` / `resume` / `cancel` 行为不变。

## Capabilities

### New Capabilities
- `api/evaluation-execution`: 评估任务的真实执行语义 —— worker 如何解析模型与题目、逐 (strategy × problem) 单元运行、记录每单元结果与成本、在预算触顶时暂停，以及模型/题目/单元失败时的处理与状态回写。

### Modified Capabilities
- `api/database-schema`: `evaluations` 表新增 `model` 列，作为真实执行解析 LLM 凭证所需的模型标识。

## Impact

- 代码：`src/tasks/evaluation.py`（worker 真实化）、`api/services/evaluation_service.py`（新增执行编排）、`api/models.py`（请求体加 `model`）、`api/db/models.py`（`Evaluation` 加 `model` 列）、新增一条 Alembic 迁移。
- 依赖 / 系统：`AlgorithmHarness`、`ProblemStore`、`auth.llm_config`、`BudgetTracker` / 成本估算、沙箱执行器。
- API 契约：创建评估请求新增必填 `model`（BREAKING）；既有客户端需补充该字段。
- 非目标：不含 #154 预算管理 API、#155 结果查询/分析 API；不改动已完成的入队时序与状态机；测试全部 mock LLM / 沙箱，不发起在线调用。
