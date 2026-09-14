# 单元测试规格文档

## 1. 测试策略概述

本项目采用 **测试驱动开发（TDD）** 方法论，遵循以下原则：

1. **先写测试，后写实现** - 每个功能先编写测试用例，确保测试失败，再实现功能使测试通过
2. **高覆盖率目标** - 单元测试覆盖率目标 ≥90%
3. **测试金字塔** - 大量单元测试 + 适量集成测试 + 少量端到端测试
4. **独立性** - 每个测试用例相互独立，可以任意顺序执行
5. **可重复性** - 测试结果可重复，不依赖外部状态

### 1.1 测试框架和工具

- **测试框架**: pytest
- **Mock库**: unittest.mock
- **覆盖率**: pytest-cov
- **Fixture管理**: pytest fixtures
- **参数化测试**: pytest.mark.parametrize

### 1.2 测试分类

| 测试类型 | 目录 | 用途 |
|---------|------|------|
| 单元测试 | `tests/` | 测试单个函数/类的行为 |
| 集成测试 | `tests/integration/` | 测试模块间协作 |
| 安全测试 | `tests/security/` | 测试沙箱隔离 |
| 性能测试 | `tests/performance/` | 测试执行性能 |

---

## 2. 核心模块测试规格

### 2.1 Models模块测试 (`tests/test_models.py`)

#### 测试目标
验证Pydantic数据模型的验证逻辑、序列化/反序列化。

#### 正常用例

**TC-M-001: 创建有效的Problem对象**
```python
def test_create_valid_problem():
    """测试创建有效的Problem对象"""
    problem = Problem(
        problem_id="test-001",
        title="Two Sum",
        description="Given an array...",
        difficulty="easy",
        tags=["array", "hash-table"],
        test_cases=[
            TestCase(
                input={"nums": [2, 7], "target": 9},
                expected_output=[0, 1]
            )
        ],
        constraints="2 <= nums.length"
    )
    
    assert problem.problem_id == "test-001"
    assert problem.difficulty == "easy"
    assert len(problem.test_cases) == 1
    assert problem.validate_completeness() is True
```

**TC-M-002: Problem对象JSON序列化**
```python
def test_problem_json_serialization():
    """测试Problem的JSON序列化和反序列化"""
    problem = Problem(...)
    
    # 序列化
    json_str = problem.model_dump_json()
    assert isinstance(json_str, str)
    assert "problem_id" in json_str
    
    # 反序列化
    problem2 = Problem.model_validate_json(json_str)
    assert problem2.problem_id == problem.problem_id
    assert problem2.test_cases[0].input == problem.test_cases[0].input
```

**TC-M-003: ExecutionResult对象创建**
```python
def test_create_execution_result():
    """测试创建ExecutionResult对象"""
    result = ExecutionResult(
        problem_id="test-001",
        strategy_name="vanilla",
        generated_code="def solution(): pass",
        status="success",
        test_results=[],
        error_message=None,
        iterations=1,
        total_tokens=350,
        execution_time_seconds=1.2,
        timestamp="2026-09-14T10:00:00"
    )
    
    assert result.is_successful() is True
    assert result.total_tokens == 350
```

#### 边界用例

**TC-M-101: 空测试用例列表**
```python
def test_problem_with_empty_test_cases():
    """测试test_cases为空时应抛出验证错误"""
    with pytest.raises(ValidationError) as exc_info:
        Problem(
            problem_id="test-001",
            title="Test",
            description="Description",
            difficulty="easy",
            tags=[],
            test_cases=[]  # 空列表
        )
    
    assert "test_cases" in str(exc_info.value)
```

**TC-M-102: 无效的difficulty值**
```python
def test_problem_with_invalid_difficulty():
    """测试无效difficulty值应抛出验证错误"""
    with pytest.raises(ValidationError):
        Problem(
            problem_id="test-001",
            title="Test",
            description="Description",
            difficulty="超难",  # 无效值
            tags=[],
            test_cases=[TestCase(...)]
        )
```

**TC-M-103: 负数token值**
```python
def test_execution_result_with_negative_tokens():
    """测试负数token应抛出验证错误"""
    with pytest.raises(ValidationError):
        ExecutionResult(
            problem_id="test-001",
            strategy_name="vanilla",
            generated_code="code",
            status="success",
            test_results=[],
            error_message=None,
            iterations=1,
            total_tokens=-100,  # 负数
            execution_time_seconds=1.0,
            timestamp="2026-09-14T10:00:00"
        )
```

#### 异常用例

**TC-M-201: 缺少必填字段**
```python
def test_problem_missing_required_field():
    """测试缺少必填字段应抛出ValidationError"""
    with pytest.raises(ValidationError) as exc_info:
        Problem(
            problem_id="test-001",
            # 缺少title
            description="Description",
            difficulty="easy",
            tags=[],
            test_cases=[TestCase(...)]
        )
    
    assert "title" in str(exc_info.value)
```

---

### 2.2 Problem Loader模块测试 (`tests/test_problem_loader.py`)

#### 测试目标
验证JSON数据集加载、验证、过滤功能。

#### 正常用例

**TC-PL-001: 加载有效的JSON数据集**
```python
def test_load_valid_dataset(tmp_path):
    """测试加载有效的JSON数据集"""
    # 创建临时JSON文件
    dataset_path = tmp_path / "problems.json"
    data = [
        {
            "problem_id": "test-001",
            "title": "Two Sum",
            "description": "Given an array...",
            "difficulty": "easy",
            "tags": ["array"],
            "test_cases": [
                {
                    "input": {"nums": [2, 7], "target": 9},
                    "expected_output": [0, 1]
                }
            ]
        }
    ]
    dataset_path.write_text(json.dumps(data))
    
    # 加载
    loader = ProblemLoader()
    problems = loader.load(str(dataset_path))
    
    assert len(problems) == 1
    assert problems[0].problem_id == "test-001"
    assert problems[0].difficulty == "easy"
```

**TC-PL-002: 按难度过滤问题**
```python
def test_filter_by_difficulty():
    """测试按难度过滤问题"""
    problems = [
        Problem(problem_id="1", difficulty="easy", ...),
        Problem(problem_id="2", difficulty="medium", ...),
        Problem(problem_id="3", difficulty="easy", ...)
    ]
    
    loader = ProblemLoader()
    easy_problems = loader.filter_problems(problems, difficulty="easy")
    
    assert len(easy_problems) == 2
    assert all(p.difficulty == "easy" for p in easy_problems)
```

**TC-PL-003: 按标签过滤问题**
```python
def test_filter_by_tags():
    """测试按标签过滤问题"""
    problems = [
        Problem(problem_id="1", tags=["array"], ...),
        Problem(problem_id="2", tags=["tree", "dfs"], ...),
        Problem(problem_id="3", tags=["array", "hash"], ...)
    ]
    
    loader = ProblemLoader()
    array_problems = loader.filter_problems(problems, tags=["array"])
    
    assert len(array_problems) == 2
    assert all("array" in p.tags for p in array_problems)
```

#### 边界用例

**TC-PL-101: 加载空数据集**
```python
def test_load_empty_dataset(tmp_path):
    """测试加载空数据集应抛出ValueError"""
    dataset_path = tmp_path / "empty.json"
    dataset_path.write_text("[]")
    
    loader = ProblemLoader()
    with pytest.raises(ValueError, match="Dataset is empty"):
        loader.load(str(dataset_path))
```

**TC-PL-102: 过滤后结果为空**
```python
def test_filter_returns_empty_list():
    """测试过滤后无匹配结果应返回空列表"""
    problems = [
        Problem(problem_id="1", difficulty="easy", ...)
    ]
    
    loader = ProblemLoader()
    hard_problems = loader.filter_problems(problems, difficulty="hard")
    
    assert hard_problems == []
```

#### 异常用例

**TC-PL-201: 加载不存在的文件**
```python
def test_load_nonexistent_file():
    """测试加载不存在的文件应抛出FileNotFoundError"""
    loader = ProblemLoader()
    
    with pytest.raises(FileNotFoundError):
        loader.load("/path/does/not/exist.json")
```

**TC-PL-202: 加载无效的JSON**
```python
def test_load_invalid_json(tmp_path):
    """测试加载格式错误的JSON应抛出JSONDecodeError"""
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text("{invalid json")
    
    loader = ProblemLoader()
    with pytest.raises(json.JSONDecodeError):
        loader.load(str(dataset_path))
```

**TC-PL-203: 数据集包含无效问题**
```python
def test_validate_dataset_with_invalid_problem(tmp_path):
    """测试数据集包含无效问题应记录错误并跳过"""
    dataset_path = tmp_path / "problems.json"
    data = [
        {
            "problem_id": "test-001",
            "title": "Valid Problem",
            "description": "...",
            "difficulty": "easy",
            "test_cases": [{"input": {}, "expected_output": []}]
        },
        {
            "problem_id": "test-002",
            # 缺少title
            "description": "...",
            "difficulty": "invalid",  # 无效difficulty
            "test_cases": []
        }
    ]
    dataset_path.write_text(json.dumps(data))
    
    loader = ProblemLoader()
    problems = loader.load(str(dataset_path))
    
    # 应只加载有效的问题
    assert len(problems) == 1
    assert problems[0].problem_id == "test-001"
```

---

### 2.3 Sandbox Executor模块测试 (`tests/test_sandbox_executor.py`)

#### 测试目标
验证代码沙箱的安全隔离、资源限制、测试执行功能。

#### 正常用例

**TC-SE-001: 执行简单的正确代码**
```python
def test_execute_simple_code():
    """测试执行简单的正确代码"""
    code = """
def solution(nums, target):
    for i in range(len(nums)):
        for j in range(i+1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []
"""
    
    test_cases = [
        TestCase(
            input={"nums": [2, 7, 11, 15], "target": 9},
            expected_output=[0, 1]
        ),
        TestCase(
            input={"nums": [3, 2, 4], "target": 6},
            expected_output=[1, 2]
        )
    ]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "success"
    assert result.all_passed is True
    assert len(result.test_results) == 2
    assert all(tc.passed for tc in result.test_results)
```

**TC-SE-002: 捕获输出比较**
```python
def test_execute_with_float_output():
    """测试浮点数输出的模糊比较"""
    code = """
def solution(x):
    return x / 3.0
"""
    
    test_cases = [
        TestCase(
            input={"x": 1},
            expected_output=0.333333  # 允许1e-6误差
        )
    ]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.all_passed is True
```

**TC-SE-003: 允许导入白名单模块**
```python
def test_execute_with_allowed_imports():
    """测试允许导入白名单中的模块"""
    code = """
import math

def solution(x):
    return math.sqrt(x)
"""
    
    test_cases = [
        TestCase(input={"x": 4}, expected_output=2.0)
    ]
    
    config = SandboxConfig(allowed_imports=["math"])
    sandbox = SandboxExecutor(config)
    result = sandbox.execute(code, test_cases)
    
    assert result.all_passed is True
```

#### 边界用例

**TC-SE-101: 执行包含语法错误的代码**
```python
def test_execute_syntax_error():
    """测试语法错误应返回syntax_error状态"""
    code = "def solution( invalid syntax"
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, [])
    
    assert result.status == "syntax_error"
    assert "Syntax error" in result.error_message
```

**TC-SE-102: 代码超时**
```python
def test_execute_timeout():
    """测试执行超时应终止并返回timeout状态"""
    code = """
def solution(n):
    while True:  # 无限循环
        pass
"""
    
    test_cases = [TestCase(input={"n": 1}, expected_output=None)]
    
    config = SandboxConfig(timeout_seconds=2)
    sandbox = SandboxExecutor(config)
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "timeout"
    assert result.all_passed is False
```

**TC-SE-103: 错误答案**
```python
def test_execute_wrong_answer():
    """测试错误答案应标记为failed"""
    code = """
def solution(nums, target):
    return [0, 0]  # 总是返回错误答案
"""
    
    test_cases = [
        TestCase(
            input={"nums": [2, 7], "target": 9},
            expected_output=[0, 1]
        )
    ]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "failed"
    assert result.all_passed is False
    assert result.test_results[0].passed is False
```

#### 异常用例（安全测试）

**TC-SE-201: 阻止文件系统访问**
```python
def test_block_file_access():
    """测试应阻止文件系统访问"""
    code = """
def solution():
    with open('/etc/passwd', 'r') as f:
        return f.read()
"""
    
    test_cases = [TestCase(input={}, expected_output=None)]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "runtime_error"
    assert "not allowed" in result.error_message.lower() or "permission" in result.error_message.lower()
```

**TC-SE-202: 阻止导入禁止模块**
```python
def test_block_forbidden_import():
    """测试应阻止导入os、subprocess等危险模块"""
    code = """
import os

def solution():
    return os.system('ls')
"""
    
    test_cases = [TestCase(input={}, expected_output=None)]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "runtime_error"
    assert "not allowed" in result.error_message or "ImportError" in result.error_message
```

**TC-SE-203: 阻止网络访问**
```python
def test_block_network_access():
    """测试应阻止网络请求"""
    code = """
import socket

def solution():
    s = socket.socket()
    s.connect(('google.com', 80))
    return 'connected'
"""
    
    test_cases = [TestCase(input={}, expected_output=None)]
    
    sandbox = SandboxExecutor(SandboxConfig())
    result = sandbox.execute(code, test_cases)
    
    assert result.status == "runtime_error"
```

---

### 2.4 LLM Client模块测试 (`tests/test_llm_client.py`)

#### 测试目标
验证LLM API调用、重试机制、多Provider支持。

#### 正常用例

**TC-LC-001: 成功生成代码（Mock）**
```python
@patch('src.llm_client.OpenAIProvider')
def test_generate_success(mock_provider):
    """测试成功生成代码"""
    # Mock Provider响应
    mock_instance = mock_provider.return_value
    mock_instance.complete.return_value = ProviderResponse(
        text="```python\ndef solution(): pass\n```",
        model="gpt-3.5-turbo",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    )
    
    config = LLMConfig(
        provider="openai",
        api_key="test-key",
        model="gpt-3.5-turbo"
    )
    client = LLMClient(config)
    
    response = client.generate("Solve this problem...")
    
    assert response.text.startswith("```python")
    assert response.usage.total_tokens == 150
    mock_instance.complete.assert_called_once()
```

**TC-LC-002: 验证重试机制**
```python
@patch('src.llm_client.OpenAIProvider')
def test_retry_on_rate_limit(mock_provider):
    """测试速率限制时自动重试"""
    mock_instance = mock_provider.return_value
    
    # 前两次调用抛出RateLimitError，第三次成功
    mock_instance.complete.side_effect = [
        ProviderRateLimitError("Rate limit"),
        ProviderRateLimitError("Rate limit"),
        ProviderResponse(
            text="```python\ncode\n```",
            model="gpt-3.5-turbo",
            usage=TokenUsage(100, 50, 150)
        )
    ]
    
    config = LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo")
    client = LLMClient(config)
    
    response = client.generate("prompt")
    
    assert response.text == "```python\ncode\n```"
    assert mock_instance.complete.call_count == 3
```

#### 边界用例

**TC-LC-101: 空响应**
```python
@patch('src.llm_client.OpenAIProvider')
def test_empty_response(mock_provider):
    """测试空响应应记录警告但不崩溃"""
    mock_instance = mock_provider.return_value
    mock_instance.complete.return_value = ProviderResponse(
        text="",
        model="gpt-3.5-turbo",
        usage=TokenUsage(100, 0, 100)
    )
    
    config = LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo")
    client = LLMClient(config)
    
    response = client.generate("prompt")
    assert response.text == ""
```

#### 异常用例

**TC-LC-201: API认证失败**
```python
@patch('src.llm_client.OpenAIProvider')
def test_authentication_error(mock_provider):
    """测试认证失败应立即抛出异常，不重试"""
    mock_instance = mock_provider.return_value
    mock_instance.complete.side_effect = ProviderAuthenticationError("Invalid API key")
    
    config = LLMConfig(provider="openai", api_key="invalid", model="gpt-3.5-turbo")
    client = LLMClient(config)
    
    with pytest.raises(LLMClientError, match="Authentication failed"):
        client.generate("prompt")
    
    # 应只调用一次，不重试
    assert mock_instance.complete.call_count == 1
```

**TC-LC-202: 超过最大重试次数**
```python
@patch('src.llm_client.OpenAIProvider')
def test_max_retries_exceeded(mock_provider):
    """测试超过最大重试次数应抛出异常"""
    mock_instance = mock_provider.return_value
    mock_instance.complete.side_effect = ProviderAPIError("Server error")
    
    config = LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo")
    client = LLMClient(config)
    
    with pytest.raises(LLMClientError, match="after 3 retries"):
        client.generate("prompt")
    
    assert mock_instance.complete.call_count == 3
```

---

### 2.5 Strategy Base模块测试 (`tests/test_strategy_base.py`)

#### 测试目标
验证策略注册、代码提取等基础功能。

#### 正常用例

**TC-SB-001: 策略注册**
```python
def test_register_strategy():
    """测试通过装饰器注册策略"""
    
    @register_strategy("test_strategy")
    class TestStrategy(Strategy):
        @property
        def name(self):
            return "test_strategy"
        
        def run(self, problem, llm_client, sandbox):
            pass
    
    assert StrategyRegistry.is_registered("test_strategy")
    assert "test_strategy" in StrategyRegistry.list_strategies()
```

**TC-SB-002: 获取策略实例**
```python
def test_get_strategy_instance():
    """测试获取已注册策略的实例"""
    
    @register_strategy("vanilla")
    class VanillaStrategy(Strategy):
        @property
        def name(self):
            return "vanilla"
        
        def run(self, problem, llm_client, sandbox):
            pass
    
    config = StrategyConfig(name="vanilla")
    strategy = StrategyRegistry.get("vanilla", config)
    
    assert isinstance(strategy, VanillaStrategy)
    assert strategy.name == "vanilla"
```

**TC-SB-003: 提取Python代码块**
```python
def test_extract_code_from_response():
    """测试从LLM响应中提取Python代码"""
    
    class TestStrategy(Strategy):
        @property
        def name(self):
            return "test"
        
        def run(self, problem, llm_client, sandbox):
            pass
    
    strategy = TestStrategy(StrategyConfig(name="test"))
    
    response = """
Here is the solution:

```python
def solution(nums, target):
    return [0, 1]
```

This works by...
"""
    
    code = strategy._extract_code(response)
    assert "def solution" in code
    assert code.strip().startswith("def solution")
```

#### 边界用例

**TC-SB-101: 重复注册策略**
```python
def test_duplicate_strategy_registration():
    """测试重复注册相同名称的策略应抛出ValueError"""
    
    @register_strategy("duplicate")
    class Strategy1(Strategy):
        @property
        def name(self):
            return "duplicate"
        
        def run(self, problem, llm_client, sandbox):
            pass
    
    with pytest.raises(ValueError, match="already registered"):
        @register_strategy("duplicate")
        class Strategy2(Strategy):
            @property
            def name(self):
                return "duplicate"
            
            def run(self, problem, llm_client, sandbox):
                pass
```

#### 异常用例

**TC-SB-201: 获取未注册的策略**
```python
def test_get_unregistered_strategy():
    """测试获取未注册的策略应抛出KeyError"""
    
    with pytest.raises(KeyError, match="not found"):
        StrategyRegistry.get("nonexistent_strategy")
```

**TC-SB-202: 响应中无代码块**
```python
def test_extract_code_no_code_block():
    """测试响应中无代码块应抛出CodeExtractionError"""
    
    class TestStrategy(Strategy):
        @property
        def name(self):
            return "test"
        
        def run(self, problem, llm_client, sandbox):
            pass
    
    strategy = TestStrategy(StrategyConfig(name="test"))
    
    response = "This is just plain text without any code block."
    
    with pytest.raises(CodeExtractionError, match="No Python code block found"):
        strategy._extract_code(response)
```

---

### 2.6 Vanilla Strategy模块测试 (`tests/test_strategies.py`)

#### 测试目标
验证vanilla策略的完整执行流程。

#### 正常用例

**TC-VS-001: 完整执行流程（Mock）**
```python
def test_vanilla_strategy_full_execution(mock_llm_client, mock_sandbox):
    """测试vanilla策略的完整执行流程"""
    
    # Mock LLM响应
    mock_llm_client.generate.return_value = LLMResponse(
        text="```python\ndef solution(nums, target): return [0, 1]\n```",
        usage=TokenUsage(100, 50, 150),
        model="gpt-3.5-turbo"
    )
    
    # Mock沙箱执行
    mock_sandbox.execute.return_value = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01
            )
        ],
        execution_time=0.01,
        all_passed=True
    )
    
    problem = Problem(
        problem_id="test-001",
        title="Two Sum",
        description="...",
        difficulty="easy",
        tags=[],
        test_cases=[TestCase(input={"nums": [2, 7], "target": 9}, expected_output=[0, 1])]
    )
    
    config = StrategyConfig(name="vanilla")
    strategy = VanillaStrategy(config)
    
    result = strategy.run(problem, mock_llm_client, mock_sandbox)
    
    assert result.status == "success"
    assert result.iterations == 1
    assert result.total_tokens == 150
    mock_llm_client.generate.assert_called_once()
    mock_sandbox.execute.assert_called_once()
```

---

### 2.7 Metrics Calculator模块测试 (`tests/test_metrics_calculator.py`)

#### 测试目标
验证指标计算的正确性。

#### 正常用例

**TC-MC-001: 计算成功率**
```python
def test_calculate_success_rate():
    """测试成功率计算"""
    results = [
        ExecutionResult(problem_id="1", status="success", test_results=[TestCaseResult(passed=True, ...)], ...),
        ExecutionResult(problem_id="2", status="failed", test_results=[TestCaseResult(passed=False, ...)], ...),
        ExecutionResult(problem_id="3", status="success", test_results=[TestCaseResult(passed=True, ...)], ...),
    ]
    
    calculator = MetricsCalculator()
    metrics = calculator.calculate_single_strategy(results, "vanilla")
    
    assert metrics.success_rate == 2/3  # 66.67%
    assert metrics.total_problems == 3
    assert metrics.successful_problems == 2
```

**TC-MC-002: 计算Token分位数**
```python
def test_calculate_token_percentiles():
    """测试Token分位数计算"""
    results = [
        ExecutionResult(total_tokens=100, ...),
        ExecutionResult(total_tokens=200, ...),
        ExecutionResult(total_tokens=300, ...),
        ExecutionResult(total_tokens=1000, ...),  # 异常值
    ]
    
    calculator = MetricsCalculator()
    metrics = calculator.calculate_single_strategy(results, "vanilla")
    
    assert metrics.token_percentiles['p50'] == 250  # 中位数
    assert metrics.token_percentiles['p90'] >= 800
```

---

## 3. 集成测试规格 (`tests/integration/test_e2e.py`)

### TC-INT-001: 端到端执行流程
```python
def test_end_to_end_execution(tmp_path):
    """测试完整的端到端执行流程"""
    
    # 1. 准备测试数据集
    dataset_path = tmp_path / "problems.json"
    dataset_path.write_text(json.dumps([
        {
            "problem_id": "test-001",
            "title": "Simple Addition",
            "description": "Return a + b",
            "difficulty": "easy",
            "tags": ["math"],
            "test_cases": [
                {"input": {"a": 1, "b": 2}, "expected_output": 3},
                {"input": {"a": 5, "b": 7}, "expected_output": 12}
            ]
        }
    ]))
    
    # 2. 配置Harness（使用Mock LLM）
    config = HarnessConfig(
        llm_config=LLMConfig(provider="mock", ...),
        sandbox_config=SandboxConfig(),
        output_dir=str(tmp_path / "output"),
        max_workers=1
    )
    
    # 3. 执行评测
    orchestrator = HarnessOrchestrator(config)
    summary = orchestrator.run(str(dataset_path), ["vanilla"])
    
    # 4. 验证结果
    assert summary.total_problems == 1
    assert summary.total_strategies == 1
    assert "vanilla" in summary.metrics
    assert summary.metrics["vanilla"].total_problems == 1
    
    # 5. 验证输出文件
    assert (tmp_path / "output" / "results.jsonl").exists()
    assert (tmp_path / "output" / "report.md").exists()
```

---

## 4. 安全测试规格 (`tests/security/test_sandbox_security.py`)

### TC-SEC-001: 综合安全测试
```python
def test_comprehensive_security():
    """测试沙箱的综合安全性"""
    
    malicious_codes = [
        # 文件IO
        "open('/etc/passwd').read()",
        "import pathlib; pathlib.Path('/tmp/test').write_text('hack')",
        
        # 网络
        "import urllib.request; urllib.request.urlopen('http://evil.com')",
        
        # 子进程
        "import subprocess; subprocess.run(['ls'])",
        
        # 系统调用
        "import os; os.system('whoami')",
    ]
    
    sandbox = SandboxExecutor(SandboxConfig())
    
    for code in malicious_codes:
        wrapped_code = f"def solution(): {code}"
        result = sandbox.execute(wrapped_code, [TestCase(input={}, expected_output=None)])
        
        assert result.status == "runtime_error", f"Failed to block: {code}"
        assert result.all_passed is False
```

---

## 5. 性能测试规格 (`tests/performance/test_performance.py`)

### TC-PERF-001: 并发执行性能
```python
def test_parallel_execution_speedup():
    """测试并发执行的加速效果"""
    
    # 准备100个问题
    problems = [create_test_problem(i) for i in range(100)]
    
    # 串行执行
    start = time.time()
    orchestrator_serial = HarnessOrchestrator(HarnessConfig(max_workers=1))
    orchestrator_serial._execute_parallel(problems, [vanilla_strategy])
    serial_time = time.time() - start
    
    # 并行执行（5 workers）
    start = time.time()
    orchestrator_parallel = HarnessOrchestrator(HarnessConfig(max_workers=5))
    orchestrator_parallel._execute_parallel(problems, [vanilla_strategy])
    parallel_time = time.time() - start
    
    # 应有至少2.5倍加速
    speedup = serial_time / parallel_time
    assert speedup >= 2.5
```

---

## 6. Pytest配置

### `pytest.ini`
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 输出设置
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=90

# 标记定义
markers =
    unit: Unit tests
    integration: Integration tests
    security: Security tests
    performance: Performance tests
    slow: Slow-running tests
```

### `conftest.py`（共享fixtures）
```python
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_llm_client():
    """Mock LLM客户端"""
    client = Mock(spec=LLMClient)
    return client

@pytest.fixture
def mock_sandbox():
    """Mock沙箱执行器"""
    sandbox = Mock(spec=SandboxExecutor)
    return sandbox

@pytest.fixture
def sample_problem():
    """示例问题"""
    return Problem(
        problem_id="test-001",
        title="Two Sum",
        description="Given an array...",
        difficulty="easy",
        tags=["array"],
        test_cases=[
            TestCase(
                input={"nums": [2, 7], "target": 9},
                expected_output=[0, 1]
            )
        ]
    )
```

---

## 7. 测试覆盖率目标

| 模块 | 覆盖率目标 | 优先级 |
|-----|-----------|--------|
| models.py | ≥95% | 高 |
| problem_loader.py | ≥90% | 高 |
| sandbox_executor.py | ≥90% | 高（安全关键） |
| llm_client.py | ≥85% | 中 |
| strategy_base.py | ≥90% | 高 |
| strategies/*.py | ≥85% | 中 |
| result_collector.py | ≥85% | 中 |
| metrics_calculator.py | ≥90% | 高 |
| report_generator.py | ≥80% | 中 |
| harness_orchestrator.py | ≥85% | 高 |
| cli.py | ≥75% | 低 |

**总体覆盖率目标**: ≥90%

---

**文档版本**: v1.0  
**创建日期**: 2026-09-14  
**对应架构版本**: v1.0
