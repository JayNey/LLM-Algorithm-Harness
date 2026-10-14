# Task 3 实现报告：执行上下文 fail-fast 解析（model + 凭证 + 题目）

- Change：evaluation-real-executor（真实评估执行体）
- 分支：comet/evaluation-real-executor
- 提交哈希：`9b2fe7d52af495d5bfcc57a3298791747e2a2582`（HEAD 起点 3a87eb0）
- TDD 模式：tdd（先写失败测试 → 观察失败 → 最小实现 → 通过）
- 状态：**DONE_WITH_CONCERNS**（详见「顾虑」与「风险信号自报」）

---

## 1. 改动摘要

在 `src/tasks/evaluation.py` **仅新增**两个模块级成员，未触碰 `run_evaluation_task` 主体、mock worker 或其它既有逻辑：

1. `_EvalContext`（`@dataclass`）：字段 `llm_config: LLMConfig`、`problem_map: dict[str, Problem]`、`missing_problems: set[str]`。
2. `_resolve_execution_context(evaluation, session_factory) -> _EvalContext`：在执行任何单元前 fail-fast 解析「model + 凭证 + 题目」。

解析顺序与语义（对齐 Design Doc §5.4 / §5.5）：

- **先 model**：`if not evaluation.model:` → 抛 `ValueError(f"Evaluation {id} has no model configured")`（可被 `match="no model"` 命中）。model 检查置于所有延迟导入之前，model 缺失时不加载任何 auth 依赖。
- **后凭证**：`api_key_id` 缺失 → 抛 `ValueError("Credential unavailable: ...")`；否则构造 `AuthService(AuthSettings())` 并调用 `auth.llm_config(api_key_id, user_id, model)`，捕获 `fastapi.HTTPException` 转成 `ValueError(f"Credential unavailable: {exc.detail}") from None`，**绝不让 HTTPException 逃逸**进 Celery（避免被误判可重试 / 泄露 HTTP 语义）。
- **最后题目**：`ProblemStore(session_factory)` 逐个 `get_by_problem_id(pid)`；命中入 `problem_map`，缺失只记入 `missing_problems` 集合，**不 fail-fast**。

实现细节：

- 凭证 / 题目相关导入（`AuthSettings`、`AuthService`、`ProblemStore`、`HTTPException`）全部置于函数内部（延迟导入），与既有 `src/tasks/imports.py` 风格一致，规避模块级循环导入。
- `_EvalContext` 的类型注解 `LLMConfig` / `Problem` / `sessionmaker` 通过 `if TYPE_CHECKING:` 块导入，配合文件既有的 `from __future__ import annotations`，运行期零导入开销、无循环依赖，且 mypy 可解析。
- 调用方 `run_evaluation_task` 已有的 `except (ValueError, FileNotFoundError)` 分支会捕获本 helper 抛出的 `ValueError` 并置 `evaluation.status = failed`（无需改动调用方，符合任务边界）。

---

## 2. 新增测试用例

新增测试全部加入**现有** `tests/test_celery_tasks.py`（按裁定，不新建 `test_evaluation_task.py`），归入新类 `TestResolveExecutionContext`，复用文件既有 `db_session` / imports 风格并新增两个局部 fixture：

- fixture `session_factory`：返回绑定内存 SQLite 的 `sessionmaker`（仅作 `ProblemStore` 构造入参，测试中被 fake 替换，不触库）。
- fixture `make_evaluation`：构造未持久化的 `Evaluation` 实例，字段可覆盖（`id/user_id/model/api_key_id/problem_ids/strategy_names`）。

四个用例（简报要求的 3 个 + 1 个为消除 mypy `str | None` 新增错误而补的 TDD 测试）：

| 用例 | 覆盖点 | 隔离方式 |
|------|--------|----------|
| `test_missing_model_fails_fast` | model=None → `ValueError` match `"no model"` | 无需 patch（在导入 auth 前抛出） |
| `test_missing_api_key_fails_fast` | api_key_id=None → `ValueError` match `"Credential unavailable"`，且**在解密前** fail-fast | patch `AuthSettings`/`AuthService`，并令 `llm_config.side_effect=AssertionError` 断言其**不被调用** |
| `test_credential_unresolvable_fails_fast` | `llm_config` 抛 `HTTPException(403)` → 转 `ValueError` match `"Credential unavailable"` | patch `AuthSettings`/`AuthService`，`llm_config.side_effect=HTTPException` |
| `test_missing_problem_recorded_not_fatal` | `["p1","missing"]` → `p1` 入 `problem_map`、`missing` 入 `missing_problems`，不抛 | patch `AuthService`（返回 sentinel LLMConfig）+ fake `ProblemStore`（`p1`→sentinel，其余→None） |

所有测试均 mock/fake `AuthService.llm_config` 与 `ProblemStore`，**未发起任何在线调用、未做真实凭证解密、未依赖 SECRET_KEY/ENCRYPTION_KEY 环境变量**。

---

## 3. RED（命令 + 失败摘要）

命令：
```
python3 -m pytest tests/test_celery_tasks.py -k "fails_fast or missing_problem_recorded" -v --no-cov
```

首轮（helper 未定义）失败摘要 —— 失败原因即「helper 未定义 / 特性缺失」：
```
tests/test_celery_tasks.py::TestResolveExecutionContext::test_missing_model_fails_fast FAILED
tests/test_celery_tasks.py::TestResolveExecutionContext::test_credential_unresolvable_fails_fast FAILED
tests/test_celery_tasks.py::TestResolveExecutionContext::test_missing_problem_recorded_not_fatal FAILED
E   ImportError: cannot import name '_resolve_execution_context' from 'src.tasks.evaluation'
================== 3 failed, 8 deselected, 1 warning in 0.75s ==================
```

补充 RED（新增 `api_key_id` 守卫前，验证守卫缺失）：
```
python3 -m pytest tests/test_celery_tasks.py -k "missing_api_key_fails_fast" -v --no-cov
E   AssertionError: llm_config must not be reached without an api_key_id
================= 1 failed, 11 deselected, 1 warning in 1.67s =================
```
→ 证明未加守卫时 `llm_config` 会被以 `None` 触达，守卫为真实缺失特性。

---

## 4. GREEN（命令 + 通过摘要）

命令：
```
python3 -m pytest tests/test_celery_tasks.py -k "fails_fast or missing_problem_recorded" -v --no-cov
```
通过摘要：
```
test_missing_model_fails_fast PASSED
test_missing_api_key_fails_fast PASSED
test_credential_unresolvable_fails_fast PASSED
test_missing_problem_recorded_not_fatal PASSED
================== 4 passed, 8 deselected, 1 warning in 1.60s ==================
```
（唯一 warning 为既有的 `api/config.py` PydanticDeprecatedSince20，与本改动无关。）

---

## 5. 回归结果

- 文件级回归：
  ```
  python3 -m pytest tests/test_celery_tasks.py -q --no-cov
  ======================== 12 passed, 1 warning in 1.54s =========================
  ```
- 全量套件（遵循 TDD 技能「跑项目整套」要求）：
  ```
  python3 -m pytest -q --no-cov -p no:cacheprovider
  ========== 1640 passed, 6 skipped, 113 warnings in 157.28s (0:02:37) ===========
  ```
  → 无失败、无新增回归；warnings 均为既有（scipy 精度、SA deprecation、pydantic deprecation），与本改动无关。

---

## 6. 门禁结果

| 门禁 | 命令 | 结果 |
|------|------|------|
| ruff | `ruff check src/tasks/evaluation.py tests/test_celery_tasks.py` | **All checks passed!**（首轮报 import 排序 I001：`fastapi` 应在 `api.*` 前，已修复为 third-party 先于 first-party） |
| black | `black --check src/tasks/evaluation.py tests/test_celery_tasks.py` | **2 files would be left unchanged**（首轮 test 文件需重排长 `with patch(...)` 行，已运行 `black` 修复后再 check 通过） |
| mypy | `mypy src/ --ignore-missing-imports` | **Found 1 error**：`api/files/parsing.py:93`（SafeLoader subclass，**既有基线错误**，非本任务文件）。本任务引入的 `src/tasks/evaluation.py:305 str | None` 错误已通过 `api_key_id` 守卫消除，**未新增任何 mypy 错误**。 |

---

## 7. 变更文件清单与 diff 规模

```
 src/tasks/evaluation.py    | 71 ++++++++++++++++++++++++++++++++-
 tests/test_celery_tasks.py | 98 ++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 168 insertions(+), 1 deletion(-)
```

- 总变更 **169 行**（168 增 / 1 删），**< 200 行**。
- 仅修改允许范围内两个文件；未触碰 `api/db/models.py`、`api/models.py`、`api/schemas.py`、`api/services/evaluation_service.py`、Alembic 迁移或任何其它文件（`git status --porcelain` 已确认仅这两项为 M）。

---

## 8. 风险信号自报（逐条对照）

| 风险信号 | 命中 | 说明 |
|----------|------|------|
| 跨模块协调改动 | **未命中** | 改动限于 `src/tasks/evaluation.py` 单文件新增；对 `api.auth`、`api.db.problem_store` 仅为**只读消费既有接口**（延迟导入），未修改这些模块。 |
| 安全敏感面（认证 / 授权 / 加解密 / SQL / 外部输入 / 密钥凭证） | **命中** | 本 helper 直接参与**凭证解析**路径：调用 `AuthService.llm_config`（内部涉及 Fernet 解密、密钥读取）。已采取的安全措施：(1) 捕获并转换 `HTTPException`→`ValueError`，`from None` 抑制上下文，避免异常链泄露凭证/HTTP 语义进入 Celery 结果或日志；(2) helper 自身**不解密、不持有明文密钥**，仅传递 `api_key_id` 引用，明文由 `AuthService` 封装在 `LLMConfig`（`SecretStr`）内；(3) `api_key_id` 缺失时在解密前 fail-fast；(4) 测试全程 mock，**无任何真实解密或在线调用**。 |
| 并发 / 锁 / 共享状态 | **未命中** | helper 为纯函数式解析，每次调用新建 `AuthService` / `ProblemStore`，无模块级可变状态、无锁。`ProblemStore` 按调用使用 `session_factory`，worker 只读 `problem_map`、不持有 session（符合 §5.5）。 |
| 数据 / schema 迁移 | **未命中** | 无模型字段改动、无 Alembic 迁移。仅读取 `Evaluation` 既有字段（`model`/`api_key_id`/`user_id`/`problem_ids`，其中 `model` 由 Task 1 引入）。 |
| 公共 API 契约变更 | **未命中** | 新增成员均以 `_` 前缀命名（`_EvalContext`、`_resolve_execution_context`），为模块内部 helper，非公共 API；未改动任何路由/schema/对外任务签名。 |
| diff 超过 200 行 | **未命中** | 总变更 169 行 < 200 行。 |

**命中的风险信号：安全敏感面（凭证解析路径）** —— 已按上述措施处置，请 reviewer 重点复核 HTTPException→ValueError 转换与 `from None` 抑制、以及 `api_key_id` 缺失守卫的语义是否符合预期。

---

## 9. 顾虑（Concerns）

1. **超出简报字面的 `api_key_id` 守卫（新增 1 个测试 + 4 行实现）**：简报/Design §5.4 骨架直接把 `evaluation.api_key_id`（类型 `str | None`）传给 `auth.llm_config(key_id: str)`，会触发新的 mypy `arg-type` 错误。为满足「mypy 不新增错误」硬门禁，且呼应任务陈述「凭证/model **缺失**抛 ValueError」，我新增了 `if not api_key_id: raise ValueError("Credential unavailable: ...")` 守卫，并按 TDD 补了 `test_missing_api_key_fails_fast`。该守卫在语义上与 Design 一致（原设计中 `None`/无效 key 也会经 `owned_key` 抛 HTTPException→转 ValueError），只是把失败点**提前到解密前**并给出更清晰的错误文案，属**行为等价的强化**而非语义变更。若 reviewer 认为应严格逐字保留骨架（不加守卫），替代方案为传 `evaluation.api_key_id or ""` 走既有 HTTPException 路径，但错误信息可读性较差。

2. **helper 尚未被 `run_evaluation_task` 调用**：按任务边界（Task 5/6 范围），本任务只新增 helper、不接线。因此当前 `run_evaluation_task` 仍使用 mock worker，`_resolve_execution_context` 暂无生产调用点。接线时需注意：调用方须传入与 `evaluation` **同一 business engine 的 session_factory**（§5.5），而非 helper 内部另建；`missing_problems` 的下游消费（worker 中 `problem_map.get` 为 None → 单元 failed + 落 `EvaluationResult`，缺失文案 `f"Problem {pid} not found in problem store"`，§5.5）需在 Task 5/6 落实，本 helper 已备好 `missing_problems` 集合供其使用。

3. **`AuthService` / `ProblemStore` 每次调用重建**：helper 每次执行都 `AuthService(AuthSettings())`（含 `PasswordHasher().hash(...)` 与 Fernet 初始化）与新建 `ProblemStore`。这与既有 `imports.py` 的 `execute_import` 模式一致（每任务构造一次），在评估任务粒度下开销可接受；若后续需要复用可考虑在 Task 5/6 的 builder 层注入，本任务未做以避免超出边界。
