# 固定预算实验指南

本文档说明如何使用 `harness experiment` 在固定计算预算下对比模型与策略，并生成可复现的对比报告（issue #15）。

## 为什么需要预算实验

不同策略调用模型的次数不同：多轮修复策略通常比单次生成消耗更多调用与 token。直接比较通过率会把"额外计算量"的影响混进结论。固定预算实验让所有组合在相同的每题预算下运行，并如实报告实际消耗。

## 基本用法

```bash
harness experiment --config experiment.json
# 指定输出目录（覆盖配置中的 output_dir）
harness experiment --config experiment.json --output-dir ./results/experiments
```

配置文件格式参见仓库根目录的 `experiment.example.json`：

```json
{
  "name": "vanilla-vs-multi-round",
  "dataset_path": "data/problems.json",
  "output_dir": "./results/experiments",
  "repeats": 1,
  "budget": {
    "max_calls": 3,
    "max_tokens": 20000,
    "max_seconds": 120
  },
  "problem_filters": { "difficulty": "easy", "limit": 10 },
  "models": [
    {
      "provider": "siliconflow",
      "api_key": "env:SILICONFLOW_API_KEY",
      "model": "Qwen/Qwen2.5-7B-Instruct",
      "temperature": 0.2,
      "max_tokens": 2000,
      "timeout": 60
    }
  ],
  "strategies": [
    { "name": "vanilla", "max_iterations": 1 },
    { "name": "multi_round_feedback", "max_iterations": 3 }
  ],
  "sandbox_config": { "backend": "docker" }
}
```

说明：

- `models` / `strategies` / `repeats` 决定组合总数：`模型数 × 策略数 × 重复数`。
- `api_key` 支持 `env:VAR` 引用，密钥不会进入配置文件或任何结果文件。
- `budget` 为每题预算（三项均可选）：`max_calls` 限制模型调用次数；`max_tokens` 按已知用量（输入 + 输出，含供应商报告的推理 token）结算；`max_seconds` 为每题墙钟时间。每道题都从全新预算开始。

## 预算如何生效

- 每次模型调用前检查预算；预算不足以支付下一次调用时停止该题，结果记录为终态 `budget_exhausted`（不属于失败分类），已完成的轮次轨迹保留可查。
- 供应商响应缺少 usage 数据时无法结算 token 用量：若实验声明了 `max_tokens`，该组合会被标记 `token_budget_unsupported`，报告明确标注其 token 预算不受支持，不会假装满足严格预算。
- 达到预算后不再发起新调用，停止原因与实际消耗记录在各组合的 `budget_ledger.json`。

## 输出与口径

```
results/experiments/exp-YYYYMMDD-HHMMSS/
├── experiment.json                        # 可复现元数据与组合清单
├── comparison.json / comparison.csv       # 机器可读对比结果
├── REPORT.md                              # 可阅读对比报告
├── panel.html                             # 交互式对比面板（Chart.js）
└── <model>__<strategy>__r<repeat>/
    ├── summary.json                       # 与普通 run 相同结构的策略汇总
    ├── <strategy>_results.json            # 每题终态结果
    └── budget_ledger.json                 # 每题实际消耗与停止原因
```

## 模型对比分析（多模型实验）

配置多个 `models` 后，`comparison.json` 会额外包含 `model_comparison` 段，`panel.html` 提供交互式面板：

- **胜率矩阵**：同策略下模型两两逐题配对——A 过 B 挂计 A 胜，双方同果计平；重复实验按题取多数结果后再配对，`budget_exhausted` 视为未解出。每格胜/平/负之和恒等于题目总数。
- **统计显著性**：对每对模型的不一致对（胜/负）做精确 McNemar 检验，报告 p 值并标注 `p<0.05` 是否显著；不一致对为 0 时标注"样本不足"，少于 5 对时提示结论保守。
- **成本效益**：按"解出题数 / 总成本"排名；定价未配置的模型显示"未知"，不参与排名，也不进入成本散点图。
- **面板图表**：能力雷达图（隐藏通过率/样例验证率/修复率/成本效益归一化）、成本 vs 准确率散点图、消耗柱状图；胜率矩阵以表格呈现。图表库 Chart.js 走 CDN，离线打开时图表区显示降级提示，表格数据不受影响。

并行执行：配置 `"execution": "parallel"` 后按 (模型, 策略, 重复) 组合粒度并行（`max_workers` 限制并发上限，默认 4）。每个组合持有独立的 harness 与预算追踪器，串行与并行产出的目录与数据结构完全一致。

## 错误分析

实验报告内置错误分析（`comparison.json` 的 `error_analysis` 段、`REPORT.md` 的"错误分析"章节、`panel.html` 的类别占比图）：

- **七类分类**：`syntax_error`（语法/缩进）、`logic_error`（输出不匹配、断言失败）、`runtime_error`（IndexError/KeyError/TypeError 等运行时异常）、`timeout_error`（执行超时）、`memory_error`（内存超限）、`api_error`（模型调用失败）、`unknown`（无法识别）。分类优先看沙箱终态，再看异常名与消息关键词；粗粒度 `failure_category` 口径不变。
- **高频模式**：错误消息取首行、数字归一化为 `N` 后聚合，报告 Top 10 模式——相同模式仅数字不同会合并计数。
- **分布**：错误类别 × 难度、类别 × 标签，均带计数与组内占比；`budget_exhausted` 与 `unsupported` 不计入失败。
- **修复建议**：规则化生成（如 IndexError → 检查列表边界；超时 → 优化复杂度）；建议仅作提示，不自动修改代码，unknown 类只给通用排查提示。

`experiment.json` 记录：题集文件 SHA-256 与确定的题目 ID 列表、git commit、每个组合的有效模型参数（脱敏）、预算定义、定价快照（单价 + 来源 + `as_of` 日期）。相同配置与题集重跑会生成新目录，不会覆盖旧实验。

报告口径：

- 总数 = 完成 + 预算未完成；预算耗尽的题目计入明确的未完成清单，不会从分母中消失。
- 通过率同时给出按总数与按完成题数两种分母；隐藏测试通过率只计有独立隐藏测试的题目（正式口径），样例验证率只反映公开/反馈测试。
- 修复率 = 首轮未通过但最终通过的完成题数 ÷ 首轮未通过的完成题数；单轮策略没有修复机会，显示为空。
- 重复 ≥ 2 次时，报告给出各指标跨重复的最小/最大范围；远端生成的随机性不宣称为位级复现。

## 成本优化建议

实验完成后，`harness optimize` 基于该实验的 `comparison.json` 给出成本优化建议：

```bash
# 性价比排名 + 三目标推荐
harness optimize --experiment results/experiments/exp-YYYYMMDD-HHMMSS

# 追加预算方案：10 美元预算、每层准确率不低于 60%
harness optimize --experiment results/experiments/exp-YYYYMMDD-HHMMSS \
  --budget 10 --min-accuracy 0.6 --objective best_value
```

- **性价比排名**：通过题数 / 总成本，降序排列；定价未配置的组合标注"未知"并排除，不显示 $0。
- **三目标推荐**：`highest_accuracy`（不看成本）、`best_value`（性价比最高）、`lowest_cost`（满足 `--min-accuracy` 的最便宜组合；无达标组合时明确说明）。
- **预算优化器**：按 easy/medium/hard 分层，为每层选"单位成本通过数最高且层准确率达标"的组合，输出估算总成本、预期准确率与覆盖题数；预算不足或无历史数据的层会明确标注。
- **产物**：实验目录下新增 `optimization.json` 与 `OPTIMIZATION.md`。

边界：推荐基于历史数据与启发式贪心，不保证未来表现一致或全局最优；定价使用当前配置，不做价格预测。

## 定价与成本

成本按模型配置计价（`pricing.json`，输入输出分别计价），并在实验元数据中保存定价快照与来源日期（`as_of`）。没有配置定价的模型，成本列显示"未知"而不是 $0——未知定价不参与任何折算。

## 现有策略

- `vanilla`：单次直接生成。
- `chain_of_thought`：单次逐步推理生成。
- `multi_round_feedback`：基于可见测试反馈的多轮修复。

## 使用个人题库（API 与网页）

在题库页导入 JSON/CSV，导入完成后，在创建实验、创建 A/B 或基准详情的运行表单中，将数据来源选为“个人题库”，再选择集合。无需服务器路径。个人集合尚未导入或为空时，表单会提供题库入口；数据集加载失败时可以重试。模型、策略和 API Key 的配置方式不变。

`GET /api/v1/datasets` 需要登录，只返回当前用户已导入的个人集合：

```json
{
  "success": true,
  "data": [{"id": "<dataset_id>", "name": "Personal problem collection", "problem_count": 12, "updated_at": 1793190000}],
  "message": "Datasets retrieved"
}
```

当前每个用户有一个合并后的个人集合；append/overwrite 沿用题库页的语义。`dataset_id` 是集合引用，上传的 `file_id` 和导入的 `job_id` 不能代替它。引用不是授权凭证：创建与 Worker 执行仍分别检查当前用户与业务记录/快照所有权。

以下三类请求恰好提供 `dataset_id` 或 `dataset_path` 之一，其余参数保持原契约：

- `POST /api/v1/experiments`：`{"dataset_id":"<id>","models":[{"model":"<model>"}],"strategies":[{"name":"vanilla"}],"api_key_id":"<key>"}`，创建后使用已有 `/experiments/{id}/run` 启动。
- `POST /api/v1/benchmarks/suites/{suite_id}/run`：`{"dataset_id":"<id>","model":"<model>","api_key_id":"<key>"}`。Suite 的题目 ID 应存在于所选集合。
- `POST /api/v1/ab-tests`：`{"dataset_id":"<id>","model":{"model":"<model>"},"strategy":{"name":"vanilla"},"prompt_variants":[{"id":"a"},{"id":"b"}],"api_key_id":"<key>"}`，创建后使用已有 `/ab-tests/{id}/run` 启动。

两个来源同时提供、同时缺失或空白字符串返回 400；不存在或属于他人的集合返回 404（不泄露其存在性）；空集合或数据不可解析返回明确的 400。原有合法 `dataset_path` 请求继续可用，仍受 `DATA_ROOT` 路径约束，网页可切换到“服务器数据集路径”。

### 快照边界、元数据与部署

实验与 A/B 在**创建时**冻结数据，基准在**创建 run 时**冻结。快照包含完整题目模型（包括 tags、difficulty、judge_config、entry_point、测试用例及 source_* 元数据），并与业务 config 一起持久化。后续覆盖个人集合、上传过期/删除或修改原路径文件，都不影响已创建业务；要使用新数据，应创建新的实验/A-B/run。

实验/A-B 的 config 及基准 run 视图中的 `dataset_snapshot` 提供 `schema_version`、`dataset_id`/`dataset_path`、`created_at`、`sha256`、`problem_count` 追溯摘要；API 列表和详情不重复返回完整题目正文。完整元数据保存在对应业务记录的 `config.dataset_snapshot.problems`，可用于后续个人标签分析。

API 与 Worker 需连接同一业务数据库。快照存于业务记录，Worker 在本机私有临时目录生成输入 JSON，执行结束、暂停或异常退出均清理临时目录；恢复时重新生成同一快照。**快照不要求 API/Worker 共享 DATA_ROOT 或 UPLOAD_DIR**，不受上传 TTL 清理影响。快照随业务记录保留，删除业务记录时一起删除；没有独立快照文件或 TTL。Worker 被操作系统强杀时可能遗留系统临时目录，应使用部署环境的系统临时目录清理策略，不要清理仍在执行中的任务目录。

新创建的合法旧路径请求也保存快照；升级前已存在且没有快照的历史任务继续使用原路径解析，恢复时仍需要其原始文件可用。CLI 本地执行契约保持不变。

### 验证命令

后端定向集成验证：`python3 -m pytest tests/test_dataset_references.py --no-cov -q`。测试通过真实导入 API 创建三类任务，覆盖用户隔离、空/不可用集合、排他参数、完整元数据、源删除、暂停恢复、新 Worker 服务实例和临时目录清理。

前端可运行 `cd frontend && npm test && npm run lint && npm run build`。浏览器表单验证先启动 Vite（`npm run dev -- --port 5180`），再运行 `PLAYWRIGHT_MODULE=<playwright模块绝对路径> CHROME_PATH=<本机Chrome可执行文件路径> node scripts/verify-dataset-references.mjs`。输出默认位于系统临时目录下的 `issue-308-browser`，可用 `DATASET_QA_DIR` 和 `DATASET_BASE_URL` 覆盖。该脚本使用模拟 API 检查真实 React 表单的请求、空态/错误重试和 390/1280 像素布局；后端执行行为由集成测试验证，测试不会调用真实模型。
