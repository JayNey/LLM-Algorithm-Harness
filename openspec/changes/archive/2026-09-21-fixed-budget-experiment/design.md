# Design: 固定预算实验与可复现对比报告

## 实现说明

### 预算控制（BudgetTracker）

- 新增 `BudgetTracker`（`src/experiment.py` 内），按题维护调用数 / token / 耗时三类预算；Harness 在每次发起模型调用前查询 `can_call()`，不允许则停止该题并记录 `budget_exhausted`。
- token 结算只使用供应商返回的已知 usage（输入 + 输出 + 推理 token）；组合内任一响应缺 usage 且声明了硬 token 预算时，该组合标记 `token_budget_unsupported`。
- 预算定义来自实验配置（每题最大调用数、最大 token、最大耗时秒，均可选）；未声明的维度不限制。

### 实验编排（experiment runner）

- 新增 `src/experiment.py`：解析实验配置 → 遍历 (模型, 策略, 重复) 组合 → 每个组合复用现有 `AlgorithmHarness` 执行一遍题集（传入 BudgetTracker）→ 落盘到 `results/experiments/<experiment_id>/<model>__<strategy>__r<n>/`，目录内沿用现有 `summary.json` / 结果文件结构，保证与现有报告与离线回归兼容。
- 可复现元数据写入实验级 `experiment.json`：题集 SHA-256 与题目 ID 列表、git commit、每组合有效模型参数、预算定义、定价快照（单价 + source + as_of 日期）、起止时间。`experiment_id` 含时间戳，重跑不覆盖旧实验。
- 预算耗尽的题目不生成伪造的失败终态，进实验级"未完成清单"；分母口径（总数 / 完成 / 未完成）在报告层统一计算。

### 对比报告（experiment report）

- 新增 `src/experiment_report.py`：从落盘结果聚合，输出 `comparison.json`、`comparison.csv`、`REPORT.md` 到实验目录。
- 指标：隐藏测试通过率、样例验证率、失败类型分布（含 budget_exhausted）、修复率（多轮策略末轮通过 / 首轮未通过）、平均调用数 / token / 耗时；按难度与标签分组；重复 ≥ 2 时给跨重复最小 / 最大范围。
- 失败类型直接沿用 result-recording 的既有分类，不新增分类；budget_exhausted 只是实验层的未完成标记。

### 未知定价（MODIFIED delta 落点）

- 成本估算路径：查不到定价时返回"未知"标记与空成本，删除默认单价折算；`pricing_metadata` 增加显式未知标记；HTML / Markdown 报告成本列显示"未知"。`pricing.json` 格式不变。

### CLI

- `src/main.py` 新增 `experiment` 子命令：`harness experiment --config <file> [--output-dir <dir>]`；提供 `experiment.example.json` 示例。现有 `run` 与 `import` 子命令不变。

### 测试策略

- 复用离线回归的假模型客户端构造固定夹具：正确解、样例过拟合（样例过 / 隐藏挂）、API 失败、无 usage 响应四类；预算与指标按手算值断言（分母对账）。
- 端到端：离线跑通 `harness experiment --config` 全流程，断言 experiment.json、comparison.json/csv、REPORT.md 存在且字段可精确断言。

## 升级判定复核

单 change 可完成；不涉及跨模块架构协调（复用现有 Harness 与结果结构）；新增 `experiment` CLI 与新模块属于本 issue 声明的范围。预计改动约 8-10 个文件（2 个新模块、3 个现有模块、2-3 个测试文件、示例配置与文档），超过 6 文件提示阈值，已提请用户确认继续 tweak。
