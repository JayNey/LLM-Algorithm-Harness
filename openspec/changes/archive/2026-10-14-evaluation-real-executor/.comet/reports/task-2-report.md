# Task 2 实现报告：EvaluationCreateRequest.model 必填 + 持久化

- **Change**：evaluation-real-executor（真实评估执行体），Task 2 / 共 9
- **分支**：comet/evaluation-real-executor
- **提交哈希**：`091c4f0d112ece6ed86df8d08fefd76f072a3ca7`
- **提交信息**：`feat(api)!: require and persist model on evaluation create (evaluation-real-executor 1.2)`（`!` 标注 BREAKING）
- **TDD**：已加载 superpowers `test-driven-development` 技能，严格 RED → GREEN → 回归。

## 改动摘要

让创建评估的请求携带**必填** `model` 并持久化到 `evaluations.model`，为后续 Task 3 的
`auth.llm_config(key_id, user_id, model)` 凭证解析提供必需入参。

生产代码（3 文件）：

1. `api/models.py` — `EvaluationCreateRequest` 新增必填字段
   `model: str = Field(..., min_length=1, description="Model name used to execute the evaluation")`；
   同步更新 `Config.json_schema_extra` 示例。
   - **protected_namespaces 校验**：字段名恰为 `model`（非 `model_` 前缀），
     以 `python3 -W error::UserWarning` 与 `warnings.simplefilter("error")` 双重确认**无 protected_namespaces 警告**，
     故未引入 `model_config = ConfigDict(protected_namespaces=())`。
2. `api/schemas.py` — `EvaluationResponse` 新增可空字段
   `model: str | None = Field(None, ...)`（可空以兼容 DB 列可空 / 历史行 / 既有直接构造 EvaluationResponse 的测试）。
3. `api/services/evaluation_service.py` —
   - `_to_response`：映射 `model=task.model`；
   - `_to_response_async`：映射 `model=evaluation.model`；
   - `create_evaluation`（Evaluation 构造）：加 `model=request.model`；
   - `create_evaluation_async`（Evaluation 构造）：加 `model=request.model`。

测试代码（8 文件）：

- `tests/test_evaluation_service_async.py` — 新增 `TestEvaluationModelPersistence`（4 用例，见下）；
  并为既有 `create_request` fixture 补 `model="gpt-4o-mini"`。
- **BREAKING 连带修复**（既有创建评估的请求/载荷缺 `model` → 会 422，属本变更必然影响，逐一补齐 `model`）：
  `tests/test_api_database.py`、`tests/test_api_auth.py`、`tests/test_api_files.py`、
  `tests/test_api_monitoring.py`、`tests/test_api_monitoring_probes.py`、
  `tests/test_api_monitoring_queue_compatibility.py`、`tests/test_api_monitoring_service.py`。

> 未修改 `src/tasks/evaluation.py`、`api/db/models.py`、迁移文件（属其它任务，遵守禁改范围）。

## 新增测试用例（TDD）

`tests/test_evaluation_service_async.py::TestEvaluationModelPersistence`，采用**真实 `EvaluationService` + 临时 SQLite**
（与生产一致 `expire_on_commit=False`），避免共享内存 session 在同步路径 `close()` 后触发 `DetachedInstanceError`：

- `test_create_evaluation_persists_model`：同步 `create_evaluation` 返回 `resp.model == "gpt-4o-mini"`，
  且经 `get_evaluation` 从 DB 回读 `model == "gpt-4o-mini"`。
- `test_create_evaluation_async_persists_model`：异步 `create_evaluation_async` 同样回读并落库 `model`。
- `test_create_evaluation_requires_model`：缺 `model` → `pytest.raises(ValidationError)`。
- `test_create_evaluation_rejects_empty_model`：`model=""` → `min_length` 校验失败 `ValidationError`。

## RED（先失败）

**命令**：
```
python3 -m pytest tests/test_evaluation_service_async.py::TestEvaluationModelPersistence -v --no-cov
```
**摘要**：`4 failed`，失败原因均为「特性缺失」而非笔误：
- `test_create_evaluation_persists_model` / `_async_`：`AttributeError: 'EvaluationResponse' object has no attribute 'model'`
- `test_create_evaluation_requires_model` / `_rejects_empty_model`：`Failed: DID NOT RAISE ValidationError`
  （实现前 `model` 被 Pydantic 默认 `extra='ignore'` 忽略，故不报错）

## GREEN（实现后通过）

**命令**：
```
python3 -m pytest tests/test_evaluation_service_async.py::TestEvaluationModelPersistence -v --no-cov
```
**摘要**：`4 passed`。

## 回归结果

- **任务指定回归**：`python3 -m pytest tests/ -k "evaluation" -q --no-cov`
  → **`81 passed, 2 skipped, 1559 deselected`**（全绿）。
- **全量套件**（TDD 技能要求跑整个项目套件，非仅本文件）：
  `python3 -m pytest tests/ -q --no-cov -m "not online"`
  → **`1636 passed, 6 skipped, 113 warnings`**（全绿，无新增失败）。
  - 中途曾出现 19 处 `model Field required` 失败，均为 BREAKING 连带（既有评估创建载荷缺 `model`），
    已全部修复后复跑至全绿。

## 质量门禁

- `ruff check api/` → **All checks passed!**
- `ruff check <8 个改动的测试文件>` → **All checks passed!**
- `black --check api/models.py api/schemas.py api/services/evaluation_service.py` →
  首次报 `would reformat api/models.py`（单行可容纳被折行），运行 `black api/models.py` 修复后
  **3 files would be left unchanged**。
- `black --check <8 个改动的测试文件>` → **8 files would be left unchanged**。
- `mypy src/ --ignore-missing-imports` → 仅 1 处错误：
  `api/files/parsing.py:93: error: Class cannot subclass "SafeLoader" (has type "Any") [misc]`。
  该文件**未被本改动触碰**（`git diff --name-only | grep parsing` 为空），属**既有、与本变更无关**的错误；
  本改动**未新增** mypy 错误。

## 变更文件清单（11 个）

生产：
- `api/models.py`
- `api/schemas.py`
- `api/services/evaluation_service.py`

测试：
- `tests/test_evaluation_service_async.py`（新增用例 + fixture 补 model）
- `tests/test_api_database.py`
- `tests/test_api_auth.py`
- `tests/test_api_files.py`
- `tests/test_api_monitoring.py`
- `tests/test_api_monitoring_probes.py`
- `tests/test_api_monitoring_queue_compatibility.py`
- `tests/test_api_monitoring_service.py`

diff 规模：`11 files changed, 110 insertions(+), 8 deletions(-)`（< 200 行）。

## 风险信号自报

- **公共 API 契约 / 对外接口变更**：命中。`POST /api/v1/evaluations` 请求新增必填 `model`（BREAKING），
  旧客户端不带 `model` 将收到 422；`EvaluationResponse` 新增可空 `model` 字段（向后兼容，加法）。
- **数据 / schema 迁移**：未命中（`Evaluation.model` 列与迁移由 Task 1 完成，本任务仅写入该列）。
- **安全敏感面**：未直接命中。本任务不触碰认证/授权/加解密/SQL 拼接/密钥；`model` 仅作为后续
  `auth.llm_config` 的入参持久化，凭证解析在 Task 3。
- 跨模块协调改动：未命中（限 api/ + tests/）。
- 并发锁共享状态：未命中。
- diff 超过 200 行：未命中（+110/-8）。

## 顾虑

- `EvaluationResponse.model` 设为**可空**（`str | None`）以兼容历史行与既有直接构造响应的测试；
  创建路径必填、响应回读可空是刻意的一致性选择（DB 列可空）。若后续要求响应也强制非空，需单独评估历史数据。
- BREAKING 连带修改触及 7 个非「评估专属」测试文件（auth/files/monitoring），因其复用创建评估端点；
  这是新增必填字段的必然影响，均已补 `model` 并全量回归验证通过。
