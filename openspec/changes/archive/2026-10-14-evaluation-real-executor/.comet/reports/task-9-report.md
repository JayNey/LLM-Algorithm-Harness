# Task 9 Report: CI 等价质量门禁全绿

**状态：DONE_WITH_CONCERNS**
**分支：** `comet/evaluation-real-executor`
**基线 HEAD：** `72e09b5`（TASK9_BASE，工作区起始干净）
**最终 HEAD：** Task 9 收尾提交 `style: satisfy CI gates for evaluation-real-executor (4.2)`（含本报告；commit 无法自含自身哈希，以 `git log --oneline -1` 为准， orchestrator 收到的回报哈希见任务返回消息）

---

## Step 1：门禁逐条运行结果

下表为**修复前**（HEAD=72e09b5 原始态）与**修复后**（同一内容树 fresh 复跑）的实际 exit code 与输出摘录。

| # | 门禁命令 | 修复前 exit | 修复后 exit | 输出摘录（修复后为最终态 fresh 复跑） |
|---|---------|:---:|:---:|--------------------------------------|
| G1 | `ruff check .` | 0 | **0** | `All checks passed!` |
| G2 | `ruff format --check .` | 1 | 1（残留均为噪音，见 §3） | 修复前 `67 files would be reformatted, 700 files already formatted`；修复后（最终提交树 fresh 复跑）`52 files would be reformatted, 716 files already formatted`（**Python 侧残留 5 个，全部非本 change 文件**；其余 47 个为 `.md`） |
| G3 | `black --check .` | 0 | **0** | `286 files would be left unchanged.` |
| G4 | `mypy src/ --ignore-missing-imports` | 1 | 1（**归属本 change 文件：0 错**） | `Found 1 error in 1 file (checked 96 source files)`，仅 `api/files/parsing.py:93: Class cannot subclass "SafeLoader" (has type "Any") [misc]` |
| G5 | `python3 scripts/find_missing_encoding.py` | 0 | **0** | `Implicit text encodings: 0` |
| G6 | `pytest tests/test_utf8_io.py -q --no-cov` | 0 | **0** | `18 passed, 1 warning in 0.94s` |
| G7 | `pytest -m "not online" --no-cov -q` | 0 | **0** | `1653 passed, 6 skipped, 113 warnings in 145.82s` |

### 判定

- **CI 实际门禁全绿**。核对 `.github/workflows/ci.yml`：lint job 仅运行 `ruff check .`、`scripts/find_missing_encoding.py`、`black --check .`；type-check job 运行 `mypy src/`；test job 运行 utf8 门禁 + 全量 pytest。**CI 从不运行 `ruff format --check`**（详见 §3 顾虑）。
- **mypy 归属分析**（按用户给定的基线噪音判定规则）：总数 **1**；归属本 change 文件（src/tasks/evaluation.py、src/models.py、api/db/models.py、api/models.py 等）**0**；基线噪音 **1**（`api/files/parsing.py:93` SafeLoader，早于 base-ref `b76aabb` 的 main 历史问题）。按"本 change 文件无 mypy 错 = 绿"判定为绿。
- 全量 pytest 修复前后均 **1653 passed / 6 skipped**，无回归。

---

## Step 2：修复列表

初始 G2（ruff format）违规共 67 文件 = 48 `.md` + 19~20 `.py`。与本 change 交集仅 3 个文件：
- `docs/superpowers/plans/2026-10-13-evaluation-real-executor.md`（**禁区文件**，禁改，保留）
- `docs/superpowers/specs/2026-10-13-evaluation-real-executor-design.md`（**禁区文件**，禁改，保留）
- `tests/test_api_monitoring.py`（本 change 允许面文件，**已修复**；其违规行本身系基线引入——`git blame` 命中 `71b1228`，是 `b76aabb` 的祖先）

执行 `ruff format` 修复 20 个 `.py` → 复跑门禁发现两类问题并回退 5 个文件（`git checkout --`），最终提交 15 个文件：

| 文件 | 修复类型 | 说明 |
|------|---------|------|
| harness/cli/debug.py | ruff format | f-string 表达式空格 `{'='*60}` → `{'=' * 60}`（输出值不变） |
| src/benchmark/report.py | ruff format | 隐式相邻字符串拼接合并（字符串值不变） |
| src/cost_strategy.py | ruff format | 同上（ValueError 消息内容逐字符不变） |
| src/experiment_panel.py | ruff format | f-string 内引号风格 ' → "（值不变） |
| src/importers/mock.py | ruff format | f-string 表达式空格 `{i+1}` → `{i + 1}` |
| src/main.py | ruff format | 字符串拼接合并（CLI 错误消息值不变） |
| src/reporting/quality_report.py | ruff format | f-string 引号风格 |
| src/strategies/few_shot_learning.py | ruff format | 字符串拼接合并（feedback 文本值不变） |
| src/strategy_base.py | ruff format | f-string 表达式空格（`Test {i+1}:` 输出值不变） |
| tests/test_api_monitoring.py | ruff format | f-string 表达式空格（本 change 允许面文件） |
| tests/test_debug_e2e.py | ruff format | f-string 表达式空格 |
| tests/test_debug_integration.py | ruff format | 删除块首空行 |
| tests/test_harness.py | ruff format | 删除块首空行 |
| tests/test_sandbox_executor.py | ruff format | 字符串拼接合并（sandbox 源码字符串值不变） |
| tests/test_windows_file_handles.py | ruff format | 字符串拼接合并 |

以上改动全部经全量回归验证为**字符串值/语义等价**（1653 passed 无回归）。

### 回退的 5 个 `.py`（不修复的理由）

1. **`src/strategies/reflexion.py`、`src/strategies/multi_round_feedback.py`、`tests/test_integration.py`** —— ruff 0.16.8 与 black 存在**头对头互斥格式**：
   - 前两处：`] = ("success" if ... else "failed")` 括号 —— ruff format 去掉、black `--check` 要求加回（ruff format 后 `black --check` 实测报 3 files would be reformatted）；
   - 第三处：`SimpleNamespace(content=\"\"\"...\")` 拆分 —— ruff 要拆、black 要合。
   **二者不可能同时绿**。CI 门禁是 black（G3，绿），`ruff format --check` 不在 CI；故保留 black 认可的基线形态。
2. **`src/importers/leetcode.py`、`src/ab_testing.py`** —— ruff format 把 `self.session.post(a, b, c  # type: ignore[arg-type] )` 式尾注多参行拆为每参一行后，`# type: ignore` 的行归属漂移，**实测破坏 G4 mypy**（错误数 1 → 7：原 `arg-type` 错误失去抑制、旧行报 `Unused "type: ignore"`）。项目配置 `warn_unused_configs = true` 使该漂移成为门禁级破坏。修复需移动/改写 `# type: ignore` 注释 = 明确禁止的"绕过门禁"手段，故回退保留基线形态。

---

## Step 3：提交

```
style: satisfy CI gates for evaluation-real-executor (4.2)
```
提交后工作区干净（`git status --porcelain` 为空）。

---

## 最终数字

- 全量 `pytest -m "not online" --no-cov`：**1653 passed, 6 skipped**（与修复前完全一致，零回归）
- `pytest tests/test_utf8_io.py`：18 passed
- ruff check / black / encoding 脚本 / 本 change 文件 mypy：**全部干净（0 violations / 0 errors）**

## 顾虑（DONE_WITH_CONCERNS 的原因）

1. **ruff format 与 black 在本仓库版本组合（ruff 0.16.8 + 当前 black）下不是子集关系**：5 个历史 `.py` 存在两者互斥的格式点（3 处头对头风格冲突、2 处 type: ignore 行归属被格式漂移破坏 mypy）。这些文件均非本 change 引入。建议后续由维护者统一 formatter 策略（如以 `ruff format` 全面替换 `black` 并同步 CI，或在 ruff 配置中固定与 black 兼容的 preview 开关）——本任务无权修改 pyproject/CI。
2. **`ruff format --check .` 残留 47 个 `.md`**（API.md、README、docs/*、openspec 归档、本 change 的 plan/design 禁区文件）：系 ruff 0.16 新增的 markdown 内嵌代码块格式化行为（`ruff format --check API.md` 单独验证可复现）。CI 不运行该门禁，black 不管 `.md`，且其中 2 个属禁改文件，故未处理。
3. git 提交时提示 committer 身份由 hostname 自动生成（`charlesleclerc@CharlesdeMacBook-Air.local`），与本 change 无关，但仓库维护者可考虑显式配置。

## 证据文件（/tmp）

`gate2_ruff_format.txt`（初始 67 文件全量 diff）、`gate4_mypy.txt`（初始 1 错）、`gate7_pytest.txt`（修复前 1653 passed）、`fix2_g4.txt`（mypy 1→7 事故取证）、`fix3_g4.txt`（回退后恢复 1 错）、`final_g7.txt`（修复后 1653 passed）、`fin_g1..g5.txt`（最终提交态 fresh 复跑）。
