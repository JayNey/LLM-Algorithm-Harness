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
pip install -r requirements.txt
```

### 3. 配置 API Key

#### 方式 1: 环境变量（推荐）

```bash
export OPENAI_API_KEY="your-openai-key"
# 或
export ANTHROPIC_API_KEY="your-anthropic-key"
```

#### 方式 2: 配置文件

复制示例配置：

```bash
cp config.example.json config.json
```

编辑 `config.json`，填入 API Key。

## 快速开始

### 运行评估

使用默认配置运行所有策略：

```bash
python3 -m src/main --dataset data/problems.json
```

### 运行特定策略

```bash
python3 -m src/main --dataset data/problems.json --strategy vanilla
```

### 限制问题数量

```bash
python3 -m src/main --dataset data/problems.json --limit 5
```

### 使用自定义配置

```bash
python3 -m src/main --dataset data/problems.json --config config.json
```

## 配置说明

### 配置文件格式

```json
{
  "dataset_path": "data/problems.json",
  "output_dir": "./results",
  "llm_config": {
    "provider": "openai",
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

### 数据集格式

```json
[
  {
    "problem_id": "two-sum",
    "title": "Two Sum",
    "description": "问题描述...",
    "difficulty": "easy",
    "tags": ["array", "hash-table"],
    "constraints": "约束条件...",
    "test_cases": [
      {
        "input": {"nums": [2, 7, 11, 15], "target": 9},
        "expected_output": [0, 1]
      }
    ]
  }
]
```

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

## 扩展开发

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

- ✅ 代码在子进程隔离执行
- ✅ 超时限制防止无限循环
- ✅ 导入白名单限制危险库
- ✅ 不执行系统级命令

## 性能优化建议

1. **并行执行**: 使用 `multiprocessing` 并行评估多个问题
2. **缓存结果**: 缓存 LLM 响应避免重复调用
3. **批量处理**: 批量提交 LLM 请求
4. **增量评估**: 只评估新增或修改的问题

## 故障排查

### API 调用失败

- 检查 API Key 是否正确设置
- 确认网络连接正常
- 查看 API 配额是否用尽

### 沙箱执行超时

- 增加 `sandbox_config.timeout_seconds`
- 检查代码是否存在无限循环

### 测试失败

- 确保所有依赖已安装
- 检查 Python 版本（需要 3.8+）

## 贡献指南

欢迎贡献！请遵循以下流程：

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

MIT License