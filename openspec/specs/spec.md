# LLM-Algorithm-Harness 项目规格说明书

## 1. 项目背景

### 1.1 背景与动机

随着大语言模型（LLM）技术的快速发展，轻量化小模型在资源受限场景下的应用需求日益增长。然而，当前小模型在算法问题求解方面表现不佳，主要挑战包括：

- **推理能力不足**：小模型缺乏复杂的多步推理能力，难以分解复杂算法问题
- **代码生成质量低**：生成的代码常包含语法错误、逻辑错误或边界条件处理不当
- **缺乏自我修正能力**：无法根据执行反馈进行自我迭代和改进
- **策略评估困难**：缺乏系统化工具来量化评估不同Harness策略（如prompt工程、分步推理、多轮反馈）的效果

### 1.2 Harness策略概述

**Harness策略**是指通过外部框架辅助LLM完成任务的方法，主要包括：

1. **Vanilla Prompting**：直接提示，一次性生成代码
2. **Chain-of-Thought (CoT)**：引导模型先生成推理步骤，再生成代码
3. **Multi-Round Feedback**：根据测试失败结果，多轮迭代修正代码
4. **ReAct-Style**：结合推理（Reasoning）和行动（Acting），逐步探索解决方案

### 1.3 目标模型特征

本项目针对以下特征的轻量化模型：

- 参数量：1B - 7B
- 上下文窗口：2K - 8K tokens
- 代表模型：Qwen-1.5B、Phi-3-mini、Gemma-2B等
- 典型应用场景：边缘设备、移动端、低成本批量推理

## 2. 业务目标

### 2.1 核心目标

1. **量化对比**：建立统一基准，对比不同Harness策略在相同问题集上的表现
2. **提升解题率**：通过迭代优化策略，将小模型算法问题解题成功率从基线提升20%以上
3. **降低成本**：优化token使用和迭代次数，在保持准确率前提下降低API调用成本
4. **加速迭代**：提供自动化评测流程，缩短策略实验周期从数天降至数小时

### 2.2 可量化指标

- **解题成功率**：测试用例全部通过的问题占比（目标：>60%）
- **平均Token消耗**：每个问题平均使用的tokens（目标：<2000 tokens/问题）
- **平均迭代次数**：多轮策略的平均修正次数（目标：<3次）
- **执行时间**：100题基准测试完成时间（目标：<30分钟）

## 3. 用户场景

### 3.1 研究人员场景

**角色**：算法研究员、提示工程师

**需求**：
- 测试新设计的Harness策略效果
- 对比不同prompt模板的性能差异
- 分析失败案例，优化策略设计

**典型工作流**：
1. 设计新的prompt模板或迭代策略
2. 运行Harness评测，获取量化指标
3. 查看详细执行日志和失败案例
4. 调整策略参数，重新评测
5. 生成对比报告，验证改进效果

### 3.2 开发人员场景

**角色**：应用开发者、集成工程师

**需求**：
- 为特定应用场景选择最优策略
- 评估不同LLM模型的实际表现
- 集成Harness框架到生产系统

**典型工作流**：
1. 准备应用相关的算法问题数据集
2. 批量测试多个候选策略
3. 根据成本和准确率选择最优方案
4. 导出配置，集成到生产环境

### 3.3 评估人员场景

**角色**：模型评测工程师、质量保证

**需求**：
- 建立标准化算法评测基准
- 定期评估模型版本更新的影响
- 生成标准化评测报告

**典型工作流**：
1. 维护标准问题数据集
2. 定期运行标准评测流程
3. 生成趋势分析报告
4. 识别性能回归问题

## 4. 功能需求

### 4.1 问题数据集管理

**FR-1.1 数据集加载**
- 支持从JSON文件加载问题数据集
- 每个问题包含：问题ID、问题描述、测试用例、难度级别、标签
- 支持多种数据集格式（LeetCode、Codeforces、自定义格式）

**FR-1.2 数据集验证**
- 自动验证数据集格式完整性
- 检查测试用例格式正确性（输入、预期输出）
- 报告缺失字段或格式错误的具体位置

**FR-1.3 问题过滤与筛选**
- 按难度级别筛选（Easy、Medium、Hard）
- 按标签筛选（数组、动态规划、图论等）
- 按问题ID范围筛选

### 4.2 策略执行引擎

**FR-2.1 策略注册与管理**
- 采用插件架构，支持动态注册新策略
- 每个策略实现统一接口：`run(problem) -> ExecutionResult`
- 支持策略参数化配置（如最大迭代次数、温度参数）

**FR-2.2 内置核心策略**

1. **Vanilla策略**：
   - 直接将问题描述转换为prompt
   - 一次性请求LLM生成Python代码
   - 不进行迭代修正

2. **Chain-of-Thought (CoT)策略**：
   - 第一步：引导LLM生成解题思路和算法步骤
   - 第二步：基于思路生成Python代码
   - 支持思路与代码分离的两阶段生成

3. **Multi-Round Feedback策略**：
   - 初始生成代码
   - 在沙箱中执行并捕获错误
   - 将错误信息反馈给LLM，要求修正
   - 迭代直到通过所有测试或达到最大轮数（默认3轮）

**FR-2.3 策略执行控制**
- 支持并行执行多个问题（线程池或进程池）
- 每个问题独立执行，互不干扰
- 支持断点续传（保存中间状态，失败后从断点恢复）

### 4.3 LLM集成层

**FR-3.1 多Provider支持**
- OpenAI API（GPT-3.5、GPT-4）
- Anthropic API（Claude系列）
- 本地模型（通过兼容OpenAI格式的本地服务，如vLLM、Ollama）

**FR-3.2 API调用管理**
- 自动重试机制（指数退避）
- 速率限制控制（避免触发429错误）
- 超时设置（默认30秒）
- 请求/响应日志记录

**FR-3.3 响应解析**
- 从LLM响应中提取Python代码块（支持markdown代码块格式）
- 处理格式错误的响应（无代码块、多个代码块等）
- 提取额外信息（如CoT策略中的推理步骤）

### 4.4 代码沙箱执行环境

**FR-4.1 安全隔离**
- 禁止文件系统访问（除沙箱临时目录）
- 禁止网络访问
- 禁止子进程创建
- 禁止导入危险模块（os.system、subprocess等）

**FR-4.2 资源限制**
- 内存限制：256MB
- CPU时间限制：5秒
- 输出大小限制：1MB

**FR-4.3 执行与捕获**
- 执行生成的代码
- 运行所有测试用例
- 捕获标准输出、标准错误
- 捕获异常信息（类型、消息、堆栈跟踪）
- 记录执行时间和内存使用

### 4.5 结果收集与持久化

**FR-5.1 结果聚合**
- 收集每个问题的执行结果
- 包含：问题ID、策略名称、生成代码、执行状态、测试通过情况、错误信息

**FR-5.2 持久化存储**
- 支持JSON格式导出
- 支持CSV格式导出（用于表格分析）
- 支持SQLite数据库存储（用于复杂查询）

**FR-5.3 查询与过滤**
- 按策略名称查询
- 按执行状态过滤（成功、失败、超时）
- 按问题难度过滤

### 4.6 指标计算与统计分析

**FR-6.1 基础指标**
- **成功率**：通过所有测试用例的问题数 / 总问题数
- **平均Token消耗**：总tokens / 问题数
- **平均执行时间**：总执行时间 / 问题数
- **平均迭代次数**（多轮策略）：总迭代次数 / 问题数

**FR-6.2 高级统计**
- 按难度分层的成功率
- 按问题类型（标签）的成功率
- Token消耗分布（最小值、最大值、中位数、90分位）
- 首次尝试成功率 vs 多轮修正后成功率

**FR-6.3 对比分析**
- 策略之间的配对t检验（判断差异显著性）
- 置信区间计算
- 效果提升百分比计算

### 4.7 报告生成

**FR-7.1 Markdown报告**
- 执行摘要（时间、问题数、策略数）
- 各策略的核心指标表格
- 策略对比图表（成功率柱状图、Token消耗箱线图）
- 失败案例列表（问题ID、错误类型、错误消息）

**FR-7.2 图表生成**
- 成功率对比柱状图
- Token消耗箱线图
- 迭代次数分布直方图
- 难度分层成功率堆叠柱状图

**FR-7.3 详细日志**
- 每个问题的完整执行trace
- LLM请求和响应原文
- 沙箱执行输出
- 支持按问题ID导出单个问题的详细日志

### 4.8 主协调器（Harness Orchestrator）

**FR-8.1 任务编排**
- 协调数据集加载、策略执行、结果收集、报告生成的完整流程
- 支持多策略批量执行
- 支持部分问题重跑（针对失败案例）

**FR-8.2 进度监控**
- 实时显示执行进度（当前问题、已完成数、剩余数）
- 显示预计剩余时间
- 支持优雅中断（Ctrl+C后保存当前结果）

**FR-8.3 错误恢复**
- 单个问题失败不影响其他问题
- 网络错误自动重试
- 记录所有错误到日志文件

## 5. 非功能需求

### 5.1 性能要求

**NFR-1.1 批量执行性能**
- 支持100+问题的批量评测
- 通过并行执行，100题基准测试应在30分钟内完成
- 支持配置并发度（默认5个并发worker）

**NFR-1.2 资源使用**
- 单个问题评测的内存占用不超过512MB
- 沙箱隔离开销应控制在10%以内
- 支持在16GB内存的机器上运行完整评测

### 5.2 安全要求

**NFR-2.1 沙箱隔离**
- 100%阻止文件系统访问（除沙箱临时目录）
- 100%阻止网络请求
- 100%阻止子进程创建
- 通过安全审计的沙箱库（如RestrictedPython）

**NFR-2.2 API密钥安全**
- API密钥通过环境变量或配置文件管理，不硬编码
- 敏感信息不写入日志文件
- 支持密钥轮换

### 5.3 可扩展性要求

**NFR-3.1 策略插件化**
- 新策略无需修改核心代码，通过继承基类实现
- 支持从外部Python模块加载策略
- 策略注册采用装饰器或配置文件

**NFR-3.2 LLM Provider扩展**
- 新增LLM Provider只需实现统一接口
- 支持自定义请求/响应转换逻辑

**NFR-3.3 数据集格式扩展**
- 支持自定义数据集解析器
- 通过配置文件指定字段映射

### 5.4 可靠性要求

**NFR-4.1 错误处理**
- 所有外部调用（LLM API、文件IO）都有异常捕获
- 网络错误自动重试（最多3次，指数退避）
- 所有错误都有清晰的错误消息和堆栈跟踪

**NFR-4.2 日志记录**
- 结构化日志（使用Python logging模块）
- 分级日志（DEBUG、INFO、WARNING、ERROR）
- 支持日志轮转，避免单个日志文件过大

### 5.5 可用性要求

**NFR-5.1 CLI界面**
- 提供友好的命令行界面（使用Click库）
- 支持`--help`查看所有命令和参数说明
- 参数验证，无效参数给出清晰提示

**NFR-5.2 配置管理**
- 支持YAML配置文件
- 支持环境变量覆盖配置
- 提供默认配置，开箱即用

**NFR-5.3 文档**
- README包含快速开始指南
- 每个模块有详细的API文档（docstrings）
- 提供策略开发示例代码

## 6. 模块清单

### 6.1 核心模块

| 模块名称 | 文件路径 | 职责 |
|---------|---------|-----|
| models | `src/models.py` | 定义核心数据结构（Problem、ExecutionResult、StrategyConfig等） |
| problem_loader | `src/problem_loader.py` | 加载和解析问题数据集，验证格式 |
| sandbox_executor | `src/sandbox_executor.py` | 安全执行代码，运行测试用例，捕获结果 |
| llm_client | `src/llm_client.py` | LLM API封装，支持多Provider，重试机制 |
| strategy_base | `src/strategy_base.py` | 策略抽象基类，策略注册机制 |
| strategies/* | `src/strategies/` | 具体策略实现（vanilla、cot、feedback） |
| result_collector | `src/result_collector.py` | 结果聚合、持久化、查询 |
| metrics_calculator | `src/metrics_calculator.py` | 指标计算、统计分析、对比检验 |
| report_generator | `src/report_generator.py` | Markdown报告、图表生成 |
| harness_orchestrator | `src/harness_orchestrator.py` | 主流程协调器，任务编排 |
| cli | `src/cli.py` | 命令行接口入口 |

### 6.2 工具模块

| 模块名称 | 文件路径 | 职责 |
|---------|---------|-----|
| logging_utils | `src/utils/logging.py` | 日志配置和辅助函数 |
| config_utils | `src/utils/config.py` | 配置文件加载和合并 |
| validators | `src/utils/validators.py` | 通用验证函数 |

## 7. 接口定义

### 7.1 问题格式（JSON Schema）

```json
{
  "problem_id": "leetcode-001",
  "title": "Two Sum",
  "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
  "difficulty": "easy",
  "tags": ["array", "hash-table"],
  "test_cases": [
    {
      "input": {"nums": [2, 7, 11, 15], "target": 9},
      "expected_output": [0, 1]
    },
    {
      "input": {"nums": [3, 2, 4], "target": 6},
      "expected_output": [1, 2]
    }
  ],
  "constraints": "2 <= nums.length <= 10^4"
}
```

### 7.2 Strategy接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class Strategy(ABC):
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 策略配置参数
        """
        self.config = config
    
    @abstractmethod
    def run(self, problem: Problem, llm_client: LLMClient, 
            sandbox_executor: SandboxExecutor) -> ExecutionResult:
        """
        执行策略，求解问题
        
        Args:
            problem: 问题对象
            llm_client: LLM客户端
            sandbox_executor: 沙箱执行器
            
        Returns:
            ExecutionResult: 执行结果
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass
```

### 7.3 LLM响应格式

期望LLM返回包含Python代码块的markdown格式：

```markdown
这是我的解题思路：
1. 使用哈希表存储已遍历的元素
2. 对每个元素，检查target-nums[i]是否在哈希表中

\```python
def solution(nums, target):
    hash_map = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in hash_map:
            return [hash_map[complement], i]
        hash_map[num] = i
    return []
\```
```

### 7.4 执行结果Schema

```python
@dataclass
class ExecutionResult:
    problem_id: str
    strategy_name: str
    generated_code: str
    status: str  # "success", "runtime_error", "timeout", "wrong_answer"
    test_results: List[TestCaseResult]
    error_message: Optional[str]
    iterations: int  # 迭代次数（多轮策略）
    total_tokens: int
    execution_time_seconds: float
    timestamp: str
```

### 7.5 指标输出Schema

```python
@dataclass
class StrategyMetrics:
    strategy_name: str
    total_problems: int
    successful_problems: int
    success_rate: float
    average_tokens: float
    average_time_seconds: float
    average_iterations: float  # 多轮策略
    token_percentiles: Dict[str, float]  # {"p50": 1200, "p90": 2500, "p99": 4000}
    by_difficulty: Dict[str, float]  # {"easy": 0.85, "medium": 0.60, "hard": 0.30}
```

## 8. 数据结构详细定义

### 8.1 Problem

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class TestCase:
    input: Dict[str, Any]
    expected_output: Any

@dataclass
class Problem:
    problem_id: str
    title: str
    description: str
    difficulty: str  # "easy" | "medium" | "hard"
    tags: List[str]
    test_cases: List[TestCase]
    constraints: Optional[str] = None
    
    def validate(self) -> bool:
        """验证问题数据完整性"""
        return (
            self.problem_id and 
            self.description and 
            len(self.test_cases) > 0 and
            self.difficulty in ["easy", "medium", "hard"]
        )
```

### 8.2 StrategyConfig

```python
@dataclass
class StrategyConfig:
    name: str
    max_iterations: int = 1
    temperature: float = 0.7
    max_tokens: int = 2000
    system_prompt: Optional[str] = None
    custom_params: Dict[str, Any] = None
```

### 8.3 ExecutionResult

```python
@dataclass
class TestCaseResult:
    test_case_index: int
    passed: bool
    actual_output: Any
    expected_output: Any
    error_message: Optional[str] = None

@dataclass
class ExecutionResult:
    problem_id: str
    strategy_name: str
    generated_code: str
    status: str
    test_results: List[TestCaseResult]
    error_message: Optional[str]
    iterations: int
    total_tokens: int
    execution_time_seconds: float
    timestamp: str
    llm_traces: List[Dict[str, Any]]  # 每轮LLM交互的trace
```

### 8.4 StrategyReport

```python
@dataclass
class StrategyReport:
    strategy_name: str
    metrics: StrategyMetrics
    execution_results: List[ExecutionResult]
    failed_problems: List[str]  # 失败的problem_id列表
    generation_timestamp: str
```

## 9. 可量化验收标准

### 9.1 功能验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| 数据集加载 | 成功加载100%符合schema的JSON文件 | 提供10个测试JSON文件，全部成功解析 |
| 策略执行 | 至少支持3种策略（vanilla、cot、feedback） | 运行测试用例，验证3种策略都能执行 |
| 沙箱隔离 | 100%阻止文件系统、网络、子进程访问 | 运行安全测试用例，验证恶意代码被阻止 |
| 报告生成 | 生成包含所有必需字段的Markdown报告 | 检查报告文件包含：摘要表格、对比图表、失败列表 |
| 并行执行 | 100题在30分钟内完成（5并发） | 实际运行100题基准，记录总耗时 |

### 9.2 性能验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| 单题执行时间 | vanilla策略单题<20秒（含LLM调用） | 统计10题的平均执行时间 |
| 内存占用 | 单worker内存<512MB | 使用memory_profiler测量峰值内存 |
| 并发扩展性 | 5并发时吞吐量是单线程的3倍以上 | 对比串行和并行执行100题的时间 |

### 9.3 质量验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| 测试覆盖率 | 单元测试覆盖率≥90% | pytest --cov报告 |
| 代码规范 | 通过ruff检查，无错误 | ruff check src/ tests/ |
| 类型检查 | 通过mypy严格模式 | mypy src/ --strict |
| 文档完整性 | 所有公开函数有docstring | 自动化检查或人工审查 |

## 10. 边界情况处理

### 10.1 输入边界

| 边界情况 | 预期行为 |
|---------|---------|
| 空数据集 | 抛出`ValueError: Dataset is empty`，不执行任何策略 |
| 问题缺少test_cases | 验证时失败，记录错误日志，跳过该问题 |
| test_cases为空列表 | 验证失败，跳过该问题 |
| 问题描述为空字符串 | 验证失败，跳过该问题 |
| difficulty不在枚举值中 | 验证失败，跳过该问题 |

### 10.2 LLM响应边界

| 边界情况 | 预期行为 |
|---------|---------|
| 响应中无代码块 | 标记为`code_extraction_failed`，记录原始响应，该问题记为失败 |
| 响应中有多个代码块 | 提取第一个Python代码块，记录警告 |
| 代码块语言标记错误 | 尝试提取任意代码块，记录警告 |
| 响应为空 | 标记为`empty_response`，重试1次，仍失败则记为失败 |
| 代码包含语法错误 | 沙箱执行时捕获SyntaxError，记录错误信息 |

### 10.3 沙箱执行边界

| 边界情况 | 预期行为 |
|---------|---------|
| 代码无限循环 | 5秒后超时终止，标记为`timeout` |
| 代码消耗过多内存 | 触发内存限制，进程被杀死，标记为`memory_error` |
| 代码尝试导入禁止模块 | RestrictedPython阻止导入，抛出ImportError |
| 代码尝试文件IO | 沙箱阻止，抛出SecurityError或IOError |
| 测试用例输入格式错误 | 捕获TypeError，记录具体错误，该测试用例标记为失败 |

### 10.4 API调用边界

| 边界情况 | 预期行为 |
|---------|---------|
| API返回429（速率限制） | 等待60秒，重试最多3次，仍失败则该问题标记为`api_error` |
| API返回500（服务器错误） | 立即重试，指数退避（1s、2s、4s），仍失败则标记为`api_error` |
| 网络超时 | 30秒超时，重试1次，仍失败则标记为`network_error` |
| API密钥无效 | 立即失败，抛出`AuthenticationError`，终止整个评测 |
| Token超限 | 标记为`token_limit_exceeded`，该问题记为失败，继续下一个问题 |

## 11. 风险清单

### 11.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 沙箱逃逸漏洞 | 高 | 低 | 使用成熟的沙箱库（RestrictedPython），定期更新依赖 |
| LLM API不稳定 | 中 | 中 | 实现robust重试机制，支持fallback到备用provider |
| 并发执行资源竞争 | 中 | 中 | 使用进程池隔离，限制最大并发数 |
| 大规模执行内存泄漏 | 高 | 低 | 每个问题独立进程，执行后释放资源，定期内存监控 |

### 11.2 成本风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| LLM API调用成本高 | 高 | 高 | 支持本地模型，提供成本预估工具，支持结果缓存避免重复调用 |
| 长时间执行占用资源 | 中 | 中 | 优化并行度，支持分批执行，提供预估时间 |

### 11.3 数据风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 数据集版权问题 | 高 | 低 | 使用公开数据集（LeetCode、APPS），提供数据来源说明 |
| 测试用例不完整 | 中 | 中 | 提供数据集验证工具，要求用户自行确认数据质量 |

### 11.4 可维护性风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| LLM API变更导致兼容性问题 | 中 | 中 | 抽象LLM客户端接口，通过适配器模式隔离变化 |
| 新策略难以集成 | 低 | 低 | 提供清晰的策略开发文档和示例，插件化架构 |

## 12. 约束条件

### 12.1 技术约束

- **Python版本**：要求Python 3.10+（使用match-case、类型联合等新特性）
- **操作系统**：支持Linux、macOS、Windows（沙箱实现需跨平台）
- **依赖管理**：使用pyproject.toml（PEP 518），不使用传统setup.py

### 12.2 外部依赖约束

- **LLM API**：需要用户提供API密钥，框架不提供默认密钥
- **网络连接**：API调用需要稳定网络连接
- **计算资源**：推荐至少4核CPU、16GB内存用于并行执行

### 12.3 安全约束

- **代码执行**：所有用户代码必须在沙箱中执行，绝对禁止直接exec()
- **敏感信息**：API密钥、日志不得包含完整代码或问题描述（避免版权问题）

## 13. 术语表

| 术语 | 定义 |
|-----|------|
| Harness | 辅助LLM完成任务的外部框架或策略 |
| Strategy | 具体的Harness实现，如vanilla、CoT、feedback等 |
| Sandbox | 隔离的代码执行环境，限制资源和权限 |
| Test Case | 包含输入和预期输出的测试样例 |
| Execution Result | 策略执行一个问题后的完整结果，包括代码、状态、指标等 |
| Provider | LLM API提供商，如OpenAI、Anthropic、本地模型 |
| Token | LLM计费单位，约等于0.75个英文单词 |
| Success Rate | 通过所有测试用例的问题占比 |
| Iteration | 多轮策略中的一次修正尝试 |

---

**文档版本**：v1.0  
**创建日期**：2026-09-14  
**最后更新**：2026-09-14  
**负责人**：项目团队
