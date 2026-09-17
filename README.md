# LLM Algorithm Harness

一套算法评估 Harness，支持多算法策略的批量运行、结果采集、指标统计、策略横向对比，用于算法迭代评估。

## 项目概述

本项目为轻量级 LLM（如 GPT-3.5、Claude Haiku）提供一个完整的算法问题求解评估框架。支持三种核心策略：

- **Vanilla**: 直接提示，无特殊引导
- **Chain of Thought (CoT)**: 分步推理引导
- **Multi-Round Feedback**: 多轮反馈迭代优化

## 特性

- **多策略支持**: 内置三种求解策略，可扩展自定义策略
- **代码沙箱**: 隔离执行环境，安全运行用户生成代码
- **详细指标**: 成功率、Token 消耗、成本估算、迭代次数统计
- **灵活过滤**: 按难度、标签、数量筛选问题集
- **结构化输出**: JSON 格式结果，便于后续分析
- **多 LLM 支持**: 支持 OpenAI、Anthropic API

## 项目结构

```
LLM-Algorithm-Harness/
├── src/
│   ├── models.py              # 数据模型定义
│   ├── problem_loader.py      # 问题数据集加载器
│   ├── llm_client.py          # LLM API 客户端
│   ├── sandbox_executor.py    # 代码沙箱执行器
│   ├── strategy_base.py       # 策略基类
│   ├── strategies/
│   │   ├── vanilla.py         # Vanilla 策略
│   │   ├── chain_of_thought.py    # CoT 策略
│   │   └── multi_round_feedback.py # 多轮反馈策略
│   ├── harness.py             # 主协调器
│   ├── main.py                # 入口程序
│   └── utils/
│       ├── config.py          # 配置工具
│       ├── logging.py         # 日志工具
│       └── validators.py      # 验证工具
├── tests/                     # 单元测试
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

## 快速开始

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
    "max_tokens": 2000
  },
  "sandbox_config": {
    "timeout_seconds": 5,
    "memory_limit_mb": 256,
    "allowed_imports": ["math", "itertools", "collections"]
  },
  "strategies": [
    {
      "name": "vanilla",
      "max_iterations": 1
    },
    {
      "name": "multi_round_feedback",
      "max_iterations": 3
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

## 运行测试

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

## 输出结果

运行完成后，结果保存在 `results/` 目录：

```
results/
├── summary.json                    # 总结报告
├── vanilla_results.json            # Vanilla 策略详细结果
├── chain_of_thought_results.json   # CoT 策略详细结果
└── multi_round_feedback_results.json
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
```

## 报告生成

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

### 注意事项

- 如果 `pricing.json` 文件格式错误或不存在，系统会自动降级到内置定价
- 未知模型使用默认定价时，会在日志中记录 WARNING 信息
- 旧版本的 `summary.json` 不包含 `pricing_metadata`，生成报告时会使用当前配置重新估算（报告中会标注"历史数据不可用"）



### 添加新策略

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
