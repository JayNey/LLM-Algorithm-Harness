# LLM Algorithm Harness

一套算法评估 Harness，支持多算法策略的批量运行、结果采集、指标统计、策略横向对比，用于算法迭代评估。

## 项目概述

本项目为轻量级 LLM（如 GPT-3.5、Claude Haiku）提供一个完整的算法问题求解评估框架。支持四种核心策略：

- **Vanilla**: 直接提示，无特殊引导
- **Chain of Thought (CoT)**: 分步推理引导
- **Multi-Round Feedback**: 多轮反馈迭代优化
- **Self-Consistency**: 生成多个候选解并通过投票选择最佳答案

## 特性

- **多策略支持**: 内置四种求解策略，可扩展自定义策略
- **代码沙箱**: 隔离执行环境，安全运行用户生成代码
- **代码质量评估**: 全面的代码质量分析，包括时间复杂度、空间复杂度、可读性和风格一致性评估
- **详细指标**: 成功率、Token 消耗、成本估算、迭代次数统计
- **灵活过滤**: 按难度、标签、数量筛选问题集
- **结构化输出**: JSON 格式结果，便于后续分析
- **多 LLM 支持**: 支持 OpenAI、Anthropic API

## 代码质量评估功能

本项目新增了全面的代码质量评估功能，超越单纯的正确性检查：

### 评估维度

1. **时间复杂度分析**
   - 静态分析（AST 循环嵌套层数识别）
   - 性能测试（不同数据规模执行时间）
   - 复杂度推断与超时标注

2. **空间复杂度分析**
   - 内存使用峰值监控
   - 内存分配模式识别
   - 空间效率评分

3. **代码可读性评分**
   - pylint 综合质量评分
   - flake8 风格检查
   - radon 圈复杂度分析

4. **代码风格一致性**
   - black 格式检查
   - 风格偏差统计
   - 代码风格报告

### 使用方式

代码质量分析默认是可选的。在评估配置中启用：

```python
from src.code_quality.analyzer import CodeQualityAnalyzer

# 创建分析器
analyzer = CodeQualityAnalyzer(
    enable_time_analysis=True,
    enable_space_analysis=True,
    enable_readability_analysis=True,
    enable_style_analysis=True
)

# 分析代码
metrics = analyzer.analyze(code, problem)
print(f"Overall quality score: {metrics.overall_score}")
```

## 项目结构

```
LLM-Algorithm-Harness/
├── src/
│   ├── models.py              # 数据模型定义
│   ├── problem_loader.py      # 问题数据集加载器
│   ├── llm_client.py          # LLM API 客户端
│   ├── sandbox_executor.py    # 代码沙箱执行器
│   ├── strategy_base.py       # 策略基类
│   ├── code_quality/          # 代码质量分析模块
│   │   ├── analyzer.py        # 主分析器
│   │   ├── time_analyzer.py   # 时间复杂度分析
│   │   ├── space_analyzer.py  # 空间复杂度分析
│   │   ├── readability_analyzer.py  # 可读性分析
│   │   └── style_analyzer.py  # 风格一致性分析
│   ├── strategies/
│   │   ├── vanilla.py         # Vanilla 策略
│   │   ├── chain_of_thought.py    # CoT 策略
│   │   ├── multi_round_feedback.py # 多轮反馈策略
│   │   └── self_consistency.py     # Self-Consistency 策略
│   ├── harness.py             # 主协调器
│   ├── main.py                # 入口程序
│   └── utils/
│       ├── config.py          # 配置工具
│       ├── logging.py         # 日志工具
│       └── validators.py      # 验证工具
├── tests/                     # 单元测试
│   └── test_code_quality/     # 代码质量测试
├── data/
│   └── problems.json          # 示例问题数据集
├── docs/                      # 文档
├── requirements.txt           # 依赖包
└── README.md

## 安装

### 1. 克隆仓库

```bash
git clone <repository-url>
cd LLM-Algorithm-Harness
```

### 2. 安装依赖

```bash
python3 -m pip install -e .
```

项目要求 Python 3.10 或更高版本。安装后会提供 `harness` 命令；也可以继续使用模块入口 `python3 -m src.main`。

### 3. 配置 API Key

#### 方式 1: 环境变量（推荐）

```bash
export OPENAI_API_KEY="your-openai-key"
# 或
export ANTHROPIC_API_KEY="your-anthropic-key"
```

#### 方式 2: 配置文件引用环境变量

复制示例配置：

```bash
cp config.example.json config.json
```

示例配置使用 `"api_key": "env:OPENAI_API_KEY"`，运行时才从环境变量读取原始值。也支持 `${OPENAI_API_KEY}` 语法；留空时会按供应商回退到 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`。

仍可直接填写密钥，但不推荐将凭证保存到文件。配置对象、日志和报告会显示 `[REDACTED]`，模型 SDK 只在初始化边界获得原始值。

### 接入硅基流动（SiliconFlow）

`provider: "siliconflow"` 预设复用 OpenAI 兼容协议，默认兼容地址 `https://api.siliconflow.cn/v1`，密钥回退顺序：显式配置 → `SILICONFLOW_API_KEY` 环境变量（也支持 `env:NAME` / `${NAME}` 引用）。

```bash
export SILICONFLOW_API_KEY="your-siliconflow-key"

# 查看可选模型（免费模型列表接口，不产生计费）
PYTHONPATH=. python3 -m src.main --config config.siliconflow.example.json --list-models

# 连接检查（同样免费；注意：生成式连接检查才会按量计费）
PYTHONPATH=. python3 -m src.main --config config.siliconflow.example.json --check-connection

# 三种策略评测（--strategy 可选 vanilla / chain_of_thought / multi_round_feedback / self_consistency）
PYTHONPATH=. python3 -m src.main --config config.siliconflow.example.json --strategy multi_round_feedback --limit 1
```

说明：

- 模型 ID 以官方模型列表为准，也可手动填写完整模型 ID（`llm_config.model`）；模型规模元数据接口未可靠提供，一律标注未知。
- 列表查询失败时按错误原因排查（401 为鉴权问题），也可直接手动配置模型 ID 运行评测。
- 示例配置见 `config.siliconflow.example.json`（无真实密钥）。
- 成本估算：未收录进 `pricing.json` 的模型按默认单价估算（报告来源标记为 `default`），可能与实际计费有偏差；可在 `pricing.json` 中为常用模型补充真实单价。
- 请求参数：策略中的 `temperature`、`max_tokens`、`system_prompt` 和 `custom_params` 会覆盖全局 `llm_config` 对应值；模型、超时和认证仍由全局配置控制，每轮 trace 会保存脱敏后的有效参数。
- 本地服务：`provider: "local"` 表示 OpenAI 兼容服务，必须设置 `base_url`；无认证的本地服务可将 `api_key` 留空。
- API 错误：客户端只对 429、5xx、超时和连接错误做有限重试；401/403 和参数错误立即失败。缺少 token usage 时报告会标注 usage 未知，不会把调用当作零成本。
- 真实 API 端到端验证位于 `tests/test_online_verification.py`，标记为 `online`：无凭证环境自动跳过，Mock 测试不构成真实 API 验证。

## 快速开始

### 导入题目数据集

使用 `import` 子命令从不同来源导入题目：

```bash
# 从本地 JSON 文件导入
harness import --source local-json --input data/new_problems.json

# 从 LeetCode 公开题目 URL 或 slug 导入
harness import --source leetcode --input https://leetcode.com/problems/two-sum/ --preview

# 从 Codeforces 公开 API 和题面导入
harness import codeforces --contest 1234 --tags dp,graphs --import-limit 50 --output data/codeforces.json --force

# 从固定版本的 LiveCodeBench 缓存导入
harness import --source livecodebench --input data/livecodebench-release-v6.json \
  --release-version release_v6 --difficulty hard --import-limit 50 --preview

# 从固定版本的 LiveCodeBench 本地缓存导入
harness import --source livecodebench --input data/livecodebench-release-v6.json \
  --release-version release_v6 --difficulty hard --import-limit 50 --preview

# 预览导入结果（不实际写入）
harness import --source local-json --input data/new_problems.json --preview

# 指定输出路径
harness import --source local-json --input data/new_problems.json --output data/custom.json

# 覆盖重复题目（默认跳过）
harness import --source local-json --input data/new_problems.json --update-strategy overwrite

# 跳过确认提示
harness import --source local-json --input data/new_problems.json --force
```

**支持的导入来源：**
- `local-json` — 本地 JSON 文件
- `leetcode` — LeetCode 公开题面、元数据和可可靠解析的公开样例
- `codeforces` — Codeforces 公开题面、样例、rating 和标签
- `livecodebench` — 固定版本的本地 JSON/JSONL 基准缓存
- `mock` — 测试用模拟数据（用于演示和测试）

LeetCode 导入只访问公开题目接口，不绕过登录、付费限制或反爬验证，也不获取官方隐藏测试。无法可靠配对样例输入/输出或提取 Python 入口时，导入结果会标记为需要人工补全，不会伪造测试数据。

详细的导入功能说明请参考 [docs/importing.md](docs/importing.md)。

### 运行评估

使用默认配置运行所有策略：

```bash
harness --dataset data/problems.json
# 等价写法
python3 -m src.main --dataset data/problems.json
```

### 运行特定策略

```bash
harness --dataset data/problems.json --strategy vanilla
```

### 限制问题数量

```bash
harness --dataset data/problems.json --limit 5
```

### 使用自定义配置

```bash
harness --config config.json
```

配置文件可使用 JSON、YAML 或 YML 格式。数据集路径已经写入配置文件时，不需要再传 `--dataset`。

命令行参数的优先级为：**显式 CLI 参数 > 配置文件 > 程序默认值**。只有实际传入的参数才会覆盖配置文件。例如：

```bash
harness --config config.yaml \
  --dataset data/problems.json \
  --output reports/run-1 \
  --difficulty medium \
  --tags array dynamic-programming \
  --limit 20
```

`--output-dir` 是 `--output` 的兼容别名。标签筛选采用任意标签匹配；使用 `harness --help` 查看完整参数。

评测默认通过本地任务服务执行。使用 `--run-id` 可固定任务身份，任务状态和每个策略/题目单元保存在 `output_dir/tasks/<run_id>.json`；中断后可用相同配置和题库执行 `--resume --run-id <run_id>`。恢复会校验配置与题库指纹，已确认完成的单元不会重复执行；取消时在途模型调用会标记为不确定，不承诺外部 API 恰好调用一次。

### 交互式调试模式

对于需要深入理解模型推理过程、测试参数调整或手动干预的场景，可以使用交互式调试模式单步执行单个问题：

```bash
harness debug --problem leetcode_1 --strategy chain_of_thought --model gpt-4
```

**主要功能：**
- **单步执行**：在生成、执行、反馈等关键步骤暂停，逐步检查
- **断点控制**：在策略关键位置设置断点
- **实时干预**：修改 prompt、调整参数（temperature、max_rounds 等）、注入自定义提示
- **轨迹可视化**：查看完整执行轨迹，导出 JSON 格式便于分析

**常用命令：**
```
(debug) break generate        # 在代码生成后设置断点
(debug) next                  # 执行下一步
(debug) set temperature 0.9   # 动态修改参数
(debug) trace                 # 查看执行轨迹摘要
(debug) export trace.json     # 导出完整轨迹
(debug) exit                  # 退出调试会话
```

详细使用指南请参考 [docs/interactive_debugging.md](docs/interactive_debugging.md)。

### 学习曲线追踪（Benchmark Suite）

对于需要长期追踪模型性能演变的场景，可以使用基准题目集管理和学习曲线追踪功能：

```bash
# 列出可用的 benchmark suites
harness benchmark --list-suites

# 运行基准评估
harness benchmark --suite benchmark.example.json

# 生成学习曲线报告（对比多个模型）
harness benchmark --suite benchmark.example.json --compare --output reports/learning_curve.md
```

**主要功能：**
- **基准题目集管理**：定义固定的题目集（frozen benchmark），确保评估一致性
- **历史数据存储**：自动保存每次评估结果，按时间戳和模型 ID 组织
- **趋势分析**：生成时间序列图，可视化模型性能变化
- **多模型对比**：在同一图表中对比不同模型或版本的性能趋势
- **统计分析**：计算性能增长率、标准差、版本间差异
- **完整报告**：生成包含趋势图、统计表和里程碑的 Markdown 报告

**Benchmark Suite 配置示例：**
```json
{
  "name": "Standard Benchmark v1.0",
  "problems": ["leetcode_1", "leetcode_2", "leetcode_15"],
  "frozen": true,
  "version": "1.0",
  "description": "固定基准题目集，用于追踪长期性能趋势"
}
```

**使用场景：**
- 追踪模型版本迭代的性能变化
- 对比不同模型在相同题目集上的表现
- 监控算法求解能力的长期趋势
- 建立可复现的评估基线

详细使用指南请参考 [docs/learning-curve-tracking.md](docs/learning-curve-tracking.md)。

## 配置说明

### 配置文件格式

```json
{
  "dataset_path": "data/problems.json",
  "output_dir": "./results",
  "llm_config": {
    "provider": "openai",
    "api_key": "env:OPENAI_API_KEY",
    "model": "gpt-3.5-turbo",
    "temperature": 0.7,
    "max_tokens": 2000,
    "timeout": 30,
    "retry_max_attempts": 3,
    "retry_backoff_seconds": 0.5
  },
  "sandbox_config": {
    "timeout_seconds": 5,
    "memory_limit_mb": 256,
    "allowed_imports": ["math", "itertools", "collections"]
  },
  "strategies": [
    {
      "name": "vanilla",
      "max_iterations": 1,
      "temperature": 0.2,
      "max_tokens": 1200,
      "system_prompt": "Return only executable Python code.",
      "custom_params": {"top_p": 0.9}
    },
    {
      "name": "multi_round_feedback",
      "max_iterations": 3
    },
    {
      "name": "self_consistency",
      "max_iterations": 1,
      "custom_params": {
        "num_candidates": 5,
        "temperature": 0.8
      }
    }
  ]
}
```

等价的 YAML 配置示例：

```yaml
dataset_path: data/problems.json
output_dir: ./results
llm_config:
  provider: openai
  api_key: env:OPENAI_API_KEY
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
    max_iterations: 1
problem_filters:
  difficulty: easy
  tags: [array]
  limit: 10
```

### 数据集格式

```json
[
  {
    "schema_version": "1.1",
    "problem_id": "two-sum",
    "title": "Two Sum",
    "description": "问题描述...",
    "difficulty": "easy",
    "tags": ["array", "hash-table"],
    "constraints": "约束条件...",
    "source_platform": "leetcode",
    "source_problem_id": "1",
    "source_url": "https://leetcode.com/problems/two-sum/",
    "source_version": "2026-09",
    "input_output_mode": "function",
    "entry_point": "solution(nums, target)",
    "judge_config": {
      "comparison": "float_tolerance",
      "float_tolerance": 0.000001,
      "whitespace": "trim",
      "output_format": "auto"
    },
    "public_test_cases": [
      {
        "input": {"nums": [2, 7, 11, 15], "target": 9},
        "expected_output": [0, 1]
      }
    ],
    "feedback_test_cases": [],
    "hidden_test_cases": [
      {
        "input": {"nums": [3, 3], "target": 6},
        "expected_output": [0, 1]
      }
    ]
  }
]
```

旧版题目中的 `test_cases` 仍然可以导入，但会保守迁移为 `public_test_cases`，并标记为仅样例验证；系统不会根据旧字段推断隐藏测试。`public_test_cases`、`feedback_test_cases` 和 `hidden_test_cases` 可以按数据集需要为空；缺失的阶段会被显式跳过，空阶段不会被当作通过。

`input_output_mode` 支持 `function` 和 `stdin_stdout`。函数题默认调用 `solution(**test_input)`，也可以用 `entry_point` 声明自定义函数或简单的 LeetCode 方法入口，例如 `solve(value)` 或 `Solution.twoSum(nums, target)`；标准输入输出题的 `TestCase.input` 使用原始字符串，程序从 stdin 读取并写入 stdout。`judge_config.comparison` 可选 `exact`、`float_tolerance` 或 `unordered`，其中 `unordered` 只对明确配置的列表结果忽略顺序；`whitespace` 可选 `exact`、`trim` 或 `tokens`。

链表、树、交互题等需要自定义序列化或交互协议的题目，可以填写 `unsupported_reason`。Harness 会将其标记为 `unsupported`，不会把它记为模型答错。

## 运行测试

### Prompt A/B 测试

同一策略的两个 prompt 版本可以按难度和标签分层后进行 A/B 测试：

```bash
harness ab-test --config ab_test.example.json
```

配置示例见 [ab_test.example.json](ab_test.example.json)。报告会输出样例/隐藏通过率、成功率差异、95% 置信区间、Fisher 或卡方检验、Welch t 检验、Token/耗时和分组统计。p-value 只表示当前样本下的统计证据，不代表远端生成具有因果或逐字可复现结论。

### 根据历史结果推荐题目

推荐器会按历史失败率分析难度、标签和标签组合，排除已评估题目，生成报告和标准题目数据集：

```bash
harness recommend \
  --history results/ \
  --dataset data/problems.json \
  --output recommended.json \
  --failure-threshold 0.5 \
  --min-samples 2 \
  --limit 20
```

也可以省略 `--dataset`，让工具从历史 `metadata.json` 或 `experiment.json` 推断题库路径。命令会生成 `recommended.json` 和同目录的 `recommended.problems.json`；后者可直接用于 `harness --dataset recommended.problems.json`。推荐报告包含失败率排名、样本数、失败类型和推荐理由。

### 运行所有测试

```bash
pytest tests/
```

### 运行特定测试文件

```bash
pytest tests/test_models.py -v
```

### 查看覆盖率

```bash
pytest --cov=src tests/
```

### 离线端到端回归与真实 API 验证的区分

| 类型 | 位置 | 网络请求 | 运行方式 |
|------|------|---------|---------|
| 离线端到端回归（替身） | `tests/test_offline_e2e.py` | 无（固定响应模型替身 + host 沙箱） | 默认 `pytest` 即运行 |
| 在线真实验证 | `tests/test_online_verification.py` | 是（硅基流动真实调用） | 标记 `online`，无凭证自动跳过 |

- **替身测试**证明链路与断言正确，**不构成**真实 API 验证；真实凭证验证记录提供商、模型 ID 与日期。
- 在线验证默认跳过；设置 `SILICONFLOW_API_KEY` 后运行 `pytest tests/test_online_verification.py -s` 即可执行并输出验证记录（模型 ID + 日期）。
- 默认 CI 不向外部模型服务发起请求；online 用例的跳过状态在输出中可见。

### 故障排查

| 现象 | 原因与处理 |
|------|-----------|
| `Sandbox preflight failed: Docker sandbox backend unavailable...` | 沙箱预检失败（评测在任何 API 调用前中止）。启动 Docker Desktop 并确认镜像存在后重跑 |
| `Unknown model '...' - using default pricing` | `pricing.json` 未收录该模型，成本按默认单价估算；可按 `pricing.example.json` 格式补充真实单价 |
| `Model listing failed: ...` | 模型列表接口失败（401 为鉴权问题）；可手动在配置中填写完整模型 ID 继续评测 |
| 全部题目 `system_error: backend_unavailable` | Docker 在运行中途掉线；启动 Docker 后重跑（评测开始前有预检，此情况仅发生在运行中途） |

## 输出结果

运行完成后，结果保存在 `results/` 目录：

```
results/
├── summary.json                    # 总结报告
├── vanilla_results.json            # Vanilla 策略详细结果
├── chain_of_thought_results.json   # CoT 策略详细结果
├── multi_round_feedback_results.json
└── self_consistency_results.json   # Self-Consistency 策略详细结果
```

### 示例输出

```
================================================================================
EVALUATION RESULTS
================================================================================

Strategy: vanilla
  Success Rate: 70.00%
  Solved: 7/10
  Avg Attempts: 1.00
  Avg Tokens: 345
  Estimated Cost: $0.0012

Strategy: chain_of_thought
  Success Rate: 80.00%
  Solved: 8/10
  Avg Attempts: 1.00
  Avg Tokens: 512
  Estimated Cost: $0.0018

Strategy: multi_round_feedback
  Success Rate: 90.00%
  Solved: 9/10
  Avg Attempts: 2.10
  Avg Tokens: 678
  Estimated Cost: $0.0024

Strategy: self_consistency
  Success Rate: 85.00%
  Solved: 8.5/10
  Avg Attempts: 5.00
  Avg Tokens: 892
  Estimated Cost: $0.0031
```

## 报告生成

实验 HTML panel 还会包含模型能力图谱：能力雷达图展示算法设计、代码实现、调试、优化和边界处理五个启发式维度，热力图表格展示按难度和标签的通过数、分母和通过率。评分来自已有实验结果，样本不足时显示未知，并附带启发式说明。

评估完成后，可以使用报告模块生成多种格式的报告，包括 CSV、Markdown、图表和 HTML。

### 支持的报告格式

- **CSV**: 结构化数据，适合导入 Excel 或数据分析工具
- **Markdown**: 可读性强的文本报告，包含表格和统计信息
- **图表**: PNG 格式的可视化图表（成功率、Token 消耗、迭代分布）
- **HTML**: 自包含的交互式报告，包含嵌入的图表

### 使用示例

```python
from src.reporting import CSVExporter, MarkdownGenerator, ChartGenerator, HTMLGenerator

# 1. 导出 CSV
CSVExporter.export_all(results_by_strategy, "reports/results.csv")

# 2. 生成 Markdown 报告
MarkdownGenerator.generate(
    metrics=metrics,
    results=results_by_strategy,
    output_path="reports/report.md",
    config={
        'model': 'gpt-4',
        'temperature': 0.7
    }
)

# 3. 生成图表
success_chart = ChartGenerator.generate_success_rate_chart(metrics)
with open("reports/success_rate.png", "wb") as f:
    f.write(success_chart.read())

token_chart = ChartGenerator.generate_token_chart(metrics)
with open("reports/token_consumption.png", "wb") as f:
    f.write(token_chart.read())

# 4. 生成 HTML 报告（包含所有图表）
HTMLGenerator.generate(
    metrics=metrics,
    results=results_by_strategy,
    output_path="reports/report.html",
    include_charts=True,
    config={'model': 'gpt-4', 'temperature': 0.7}
)
```

### 运行示例脚本

项目包含一个完整的示例脚本，演示如何生成所有格式的报告：

```bash
python3 examples/generate_reports.py
```

这会在 `examples/sample_reports/` 目录生成：
- `results.csv` - CSV 格式的结果数据
- `report.md` - Markdown 格式的报告
- `report.html` - 交互式 HTML 报告
- `charts/` - 单独的图表文件（PNG 格式）

### 报告内容

生成的报告包含以下内容：

- **策略性能摘要**: 各策略的成功率、解决问题数、平均 Token 消耗
- **难度分层统计**: 按 easy/medium/hard 分类的性能指标
- **失败案例汇总**: 列出失败的问题及错误信息
- **正式评测边界**: 展示正式可评测题数、隐藏测试通过率和仅样例题数
- **可视化图表**:
  - 成功率柱状图（颜色编码：绿色 ≥80%，黄色 50-80%，红色 <50%）
  - Token 消耗折线图
  - 迭代次数分布直方图（仅多轮策略）

### CSV 格式说明

CSV 文件包含以下列：

| 列名 | 说明 |
|------|------|
| problem_id | 问题 ID |
| strategy | 策略名称 |
| status | 执行状态 (success/failed) |
| passed | 是否通过所有测试 |
| tokens | 总 Token 消耗 |
| time | 执行时间（秒） |
| iterations | 迭代次数 |
| error_message | 错误信息（如果失败） |
| total_tests | 总测试用例数 |
| passed_tests | 通过的测试用例数 |
| failed_tests | 失败的测试用例数 |
| formal_evaluable | 是否有独立隐藏评测用例 |
| formal_passed | 隐藏评测是否全部通过 |
| sample_only | 是否仅有公开/反馈测试 |
| hidden_total_tests | 隐藏测试总数 |
| hidden_passed_tests | 隐藏测试通过数 |
| hidden_failed_tests | 隐藏测试失败数 |

CSV 文件使用 UTF-8 BOM 编码，确保在 Excel 中正确显示中文。

## 固定预算实验（模型与策略对比）

不同策略调用模型的次数不同，直接比较通过率会混入额外计算量的影响。`harness experiment` 让模型 × 策略 × 重复组合在相同的每题预算（调用数 / token / 耗时）下运行，输出隐藏测试通过率、样例验证率、失败类型、修复率与实际消耗的可复现对比报告：

```bash
harness experiment --config experiment.json
```

多模型实验会额外输出胜率矩阵、精确 McNemar 显著性标注、成本效益排名和交互式对比面板 `panel.html`（雷达图 / 成本-准确率散点图 / 消耗柱状图），并支持 `"execution": "parallel"` 组合粒度并行。配置格式、预算生效方式与报告口径详见 [docs/experiments.md](docs/experiments.md)；示例配置见 `experiment.example.json`。未配置定价的模型成本显示"未知"，不会按默认单价折算。

基于实验数据还能一键生成成本优化建议（性价比排名、三目标组合推荐、给定预算下的分层方案）：

```bash
harness optimize --experiment results/experiments/exp-YYYYMMDD-HHMMSS --budget 10 --min-accuracy 0.6
```

## 自定义模型定价

Harness 支持用户自定义 LLM 模型定价，用于准确估算评估成本。

### 定价策略

成本估算采用三级降级策略：

1. **自定义定价** (`pricing.json`) - 用户提供的定价配置，优先级最高
2. **内置定价** - Harness 内置的常见模型定价（GPT-4、Claude 3 等）
3. **默认定价** - 未知模型使用默认值，并记录警告日志

### 配置方法

#### 1. 创建 `pricing.json`

在项目根目录创建 `pricing.json` 文件：

```json
{
  "models": {
    "gpt-4o": {
      "prompt_price_per_1k": 0.0025,
      "completion_price_per_1k": 0.01
    },
    "gpt-4o-mini": {
      "prompt_price_per_1k": 0.00015,
      "completion_price_per_1k": 0.0006
    },
    "claude-3.5-sonnet": {
      "prompt_price_per_1k": 0.003,
      "completion_price_per_1k": 0.015
    }
  }
}
```

项目提供了 `pricing.example.json` 示例文件，包含常见模型的定价配置。

#### 2. 定价格式说明

- `prompt_price_per_1k`: 每 1000 个 prompt tokens 的价格（美元）
- `completion_price_per_1k`: 每 1000 个 completion tokens 的价格（美元）

#### 3. 模型匹配规则

PricingManager 按以下顺序匹配模型：

1. **精确匹配**: 完全匹配模型名称（如 `gpt-4-turbo-2024-04-09`）
2. **前缀匹配**: 匹配模型名称前缀（如 `gpt-4-turbo` 匹配所有 `gpt-4-turbo-*` 模型）
3. **降级默认**: 使用默认定价并记录警告

### 历史数据准确性保障

定价元数据会随评估结果保存到 `summary.json`：

```json
{
  "strategies": {
    "vanilla": {
      "success_rate": 0.8,
      "estimated_cost_usd": 0.0156,
      "pricing_metadata": {
        "model": "gpt-4o",
        "prompt_price_per_1k": 0.0025,
        "completion_price_per_1k": 0.01,
        "source": "custom",
        "has_actual_pricing": true
      }
    }
  }
}
```

**定价来源标识**：
- `custom`: 来自 `pricing.json` 自定义配置
- `builtin`: 来自 Harness 内置定价
- `default`: 使用默认值（未知模型）

生成报告时优先使用 `summary.json` 中的历史定价数据，确保即使模型定价更新，历史评估的成本估算仍然准确。

### 使用示例

```bash
# 1. 创建自定义定价配置
cp pricing.example.json pricing.json
# 编辑 pricing.json 设置实际定价

# 2. 运行评估
harness --dataset data/problems.json --model gpt-4o

# 3. 查看成本估算
cat results/summary.json | jq '.strategies.vanilla.pricing_metadata'
```

生成的 HTML 和 Markdown 报告会显示成本估算和定价来源。

## 策略说明

### Vanilla
直接提示策略，不包含特殊引导或推理步骤。适合简单问题或测试基准性能。

### Chain of Thought (CoT)
引导模型进行分步推理，通过"让我们一步步思考"的方式提高复杂问题的求解准确率。

### Multi-Round Feedback
多轮反馈迭代优化策略。根据测试结果提供反馈，让模型修正代码，最多进行配置的最大迭代次数。

### Self-Consistency
生成多个候选解（默认 5 个）并通过投票选择最频繁的正确答案。通过高温度采样（默认 0.8）增加候选解的多样性，适合有多种求解路径的问题。

**配置参数：**
- `num_candidates`: 生成的候选解数量（默认 5）
- `temperature`: 采样温度（默认 0.8，可通过 custom_params 配置）

**适用场景：**
- 有多种求解思路的问题
- 需要提高鲁棒性的场景
- 对准确率要求高于效率的情况

## 注意事项

- 如果 `pricing.json` 文件格式错误或不存在，系统会自动降级到内置定价
- 未知模型使用默认定价时，会在日志中记录 WARNING 信息
- 旧版本的 `summary.json` 不包含 `pricing_metadata`，生成报告时会使用当前配置重新估算（报告中会标注"历史数据不可用"）

## 添加新策略

1. 在 `src/strategies/` 创建新文件
2. 继承 `StrategyBase` 类
3. 实现 `execute()` 方法
4. 在 `harness.py` 的 `STRATEGY_MAP` 注册

```python
from src.strategy_base import StrategyBase

class MyStrategy(StrategyBase):
    def execute(self, problem: Problem) -> ExecutionResult:
        # 实现策略逻辑
        pass
```

### 添加新的 LLM 提供商

在 `src/llm_client.py` 中添加新的 provider 分支：

```python
elif self.config.provider == "new_provider":
    return self._call_new_provider(prompt, system_prompt)
```

## 架构设计

系统采用分层架构：

```
┌─────────────────────────────────────┐
│      Main Harness (Coordinator)     │
├─────────────────────────────────────┤
│  Problem Loader │ Strategy Manager  │
├─────────────────────────────────────┤
│  LLM Client  │  Sandbox Executor   │
├─────────────────────────────────────┤
│     Strategies (Vanilla/CoT/MRF)    │
└─────────────────────────────────────┘
```

## 安全考虑

- 代码在子进程隔离执行
- 超时限制防止无限循环
- 导入白名单限制危险库
- 不执行系统级命令

## 性能优化建议

1. **并行执行**: 使用 `multiprocessing` 并行评估多个问题
2. **缓存结果**: 缓存 LLM 响应避免重复调用
3. **批量处理**: 批量提交 LLM 请求
4. **增量评估**: 只评估新增或修改的问题

## 故障排查

### 代码沙箱

生产配置默认使用 Docker 执行模型生成代码。Docker 后端会禁用网络、使用只读根文件系统、移除容器 capabilities，并限制内存、进程数和输出大小；请先启动 Docker Desktop 并准备配置中的镜像。

```yaml
sandbox_config:
  backend: docker
  docker_image: python:3.11-slim
  timeout_seconds: 5
  memory_limit_mb: 256
  max_output_bytes: 1000000
  max_processes: 16
```

Docker 不可用时评测会返回明确的 `backend_unavailable` 失败，不会偷偷退回宿主进程。`backend: host` 只适合单元测试，不具备生产隔离能力。

### API 调用失败

- 检查 API Key 是否正确设置
- 确认网络连接正常
- 查看 API 配额是否用尽

### 沙箱执行超时

- 增加 `sandbox_config.timeout_seconds`
- 检查代码是否存在无限循环

### 测试失败

- 确保所有依赖已安装
- 检查 Python 版本（需要 3.10+）

## 贡献指南

欢迎贡献！请遵循以下流程：

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

MIT License
