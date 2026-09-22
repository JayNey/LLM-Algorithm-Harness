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

`experiment.json` 记录：题集文件 SHA-256 与确定的题目 ID 列表、git commit、每个组合的有效模型参数（脱敏）、预算定义、定价快照（单价 + 来源 + `as_of` 日期）。相同配置与题集重跑会生成新目录，不会覆盖旧实验。

报告口径：

- 总数 = 完成 + 预算未完成；预算耗尽的题目计入明确的未完成清单，不会从分母中消失。
- 通过率同时给出按总数与按完成题数两种分母；隐藏测试通过率只计有独立隐藏测试的题目（正式口径），样例验证率只反映公开/反馈测试。
- 修复率 = 首轮未通过但最终通过的完成题数 ÷ 首轮未通过的完成题数；单轮策略没有修复机会，显示为空。
- 重复 ≥ 2 次时，报告给出各指标跨重复的最小/最大范围；远端生成的随机性不宣称为位级复现。

## 定价与成本

成本按模型配置计价（`pricing.json`，输入输出分别计价），并在实验元数据中保存定价快照与来源日期（`as_of`）。没有配置定价的模型，成本列显示"未知"而不是 $0——未知定价不参与任何折算。

## 现有策略

- `vanilla`：单次直接生成。
- `chain_of_thought`：单次逐步推理生成。
- `multi_round_feedback`：基于可见测试反馈的多轮修复。
