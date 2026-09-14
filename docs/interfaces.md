# API接口定义文档

## 1. 接口概览

本文档定义所有核心接口（抽象基类和协议），确保模块间的解耦和可扩展性。

## 2. Strategy接口（策略抽象）

### 2.1 Strategy抽象基类

```python
from abc import ABC, abstractmethod
from typing import Optional
import re

class Strategy(ABC):
    """
    策略抽象基类
    
    所有Harness策略必须继承此类并实现run()方法。
    """
    
    def __init__(self, config: StrategyConfig):
        """
        初始化策略
        
        Args:
            config: 策略配置对象
        """
        self.config = config
        self.logger = get_logger(f"strategy.{self.name}")
    
    @abstractmethod
    def run(
        self, 
        problem: Problem, 
        llm_client: 'LLMClient', 
        sandbox_executor: 'SandboxExecutor'
    ) -> ExecutionResult:
        """
        执行策略，求解问题
        
        Args:
            problem: 问题对象
            llm_client: LLM客户端实例
            sandbox_executor: 沙箱执行器实例
            
        Returns:
            ExecutionResult: 执行结果，包含生成代码、测试结果、指标等
            
        Raises:
            StrategyExecutionError: 策略执行失败
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        策略名称
        
        Returns:
            str: 策略的唯一标识符，如 "vanilla", "cot", "feedback"
        """
        pass
    
    def _extract_code(self, response: str) -> str:
        """
        从LLM响应中提取Python代码
        
        支持的格式：
        - ```python ... ```
        - ```py ... ```
        - ``` ... ``` (无语言标记)
        
        Args:
            response: LLM的原始响应文本
            
        Returns:
            str: 提取的Python代码
            
        Raises:
            CodeExtractionError: 未找到代码块
        """
        # 优先匹配 python 标记
        pattern = r'```python\s*(.*?)\s*```'
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        # 尝试匹配 py 标记
        pattern = r'```py\s*(.*?)\s*```'
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        # 尝试匹配无语言标记的代码块
        pattern = r'```\s*(.*?)\s*```'
        match = re.search(pattern, response, re.DOTALL)
        
        if match:
            code = match.group(1).strip()
            # 简单检查是否像Python代码（包含def或import）
            if 'def ' in code or 'import ' in code or 'class ' in code:
                return code
        
        raise CodeExtractionError(
            f"No Python code block found in response. "
            f"Response preview: {response[:200]}..."
        )
    
    def _build_base_prompt(self, problem: Problem) -> str:
        """
        构建基础prompt（子类可复用）
        
        Args:
            problem: 问题对象
            
        Returns:
            str: 基础prompt文本
        """
        prompt = f"""Solve the following algorithmic problem in Python:

**Problem**: {problem.title}

**Description**:
{problem.description}

**Constraints**:
{problem.constraints or 'None specified'}

**Requirements**:
1. Implement a function that solves the problem
2. The function should handle all test cases correctly
3. Consider edge cases and boundary conditions
4. Optimize for clarity and correctness

Please provide only the Python code implementation, wrapped in a markdown code block.
"""
        return prompt


class CodeExtractionError(Exception):
    """代码提取失败异常"""
    pass


class StrategyExecutionError(Exception):
    """策略执行失败异常"""
    pass
```

**关键方法**：
- `run()`: 核心执行逻辑，必须由子类实现
- `name`: 策略唯一标识符，用于注册和查找
- `_extract_code()`: 通用代码提取方法，子类可直接使用
- `_build_base_prompt()`: 基础prompt构建，子类可扩展

---

### 2.2 StrategyRegistry（策略注册表）

```python
from typing import Dict, Type, List

class StrategyRegistry:
    """
    策略注册表（单例模式）
    
    管理所有已注册的策略类，支持动态注册和查找。
    """
    
    _strategies: Dict[str, Type[Strategy]] = {}
    
    @classmethod
    def register(cls, name: str, strategy_class: Type[Strategy]):
        """
        注册策略类
        
        Args:
            name: 策略名称
            strategy_class: 策略类（必须继承Strategy）
            
        Raises:
            ValueError: 策略名已存在或策略类无效
        """
        if name in cls._strategies:
            raise ValueError(f"Strategy '{name}' is already registered")
        
        if not issubclass(strategy_class, Strategy):
            raise ValueError(
                f"Strategy class must inherit from Strategy, "
                f"got {strategy_class}"
            )
        
        cls._strategies[name] = strategy_class
        logger.info(f"Registered strategy: {name}")
    
    @classmethod
    def get(cls, name: str, config: Optional[StrategyConfig] = None) -> Strategy:
        """
        获取策略实例
        
        Args:
            name: 策略名称
            config: 策略配置（可选，使用默认配置）
            
        Returns:
            Strategy: 策略实例
            
        Raises:
            KeyError: 策略未注册
        """
        if name not in cls._strategies:
            raise KeyError(
                f"Strategy '{name}' not found. "
                f"Available strategies: {list(cls._strategies.keys())}"
            )
        
        strategy_class = cls._strategies[name]
        
        if config is None:
            config = StrategyConfig(name=name)
        
        return strategy_class(config)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """
        列出所有已注册的策略名称
        
        Returns:
            List[str]: 策略名称列表
        """
        return list(cls._strategies.keys())
    
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """
        检查策略是否已注册
        
        Args:
            name: 策略名称
            
        Returns:
            bool: 是否已注册
        """
        return name in cls._strategies


def register_strategy(name: str):
    """
    策略注册装饰器
    
    使用方式：
        @register_strategy("my_strategy")
        class MyStrategy(Strategy):
            ...
    
    Args:
        name: 策略名称
        
    Returns:
        装饰器函数
    """
    def decorator(cls: Type[Strategy]):
        StrategyRegistry.register(name, cls)
        return cls
    
    return decorator
```

**使用示例**：
```python
@register_strategy("vanilla")
class VanillaStrategy(Strategy):
    @property
    def name(self) -> str:
        return "vanilla"
    
    def run(self, problem, llm_client, sandbox):
        # 实现逻辑
        pass
```

---

## 3. LLM Client接口

### 3.1 BaseProvider抽象类

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseProvider(ABC):
    """
    LLM Provider抽象基类
    
    所有LLM服务提供商必须实现此接口。
    """
    
    def __init__(self, api_key: str, **kwargs):
        """
        初始化Provider
        
        Args:
            api_key: API密钥
            **kwargs: 额外配置参数
        """
        self.api_key = api_key
        self.config = kwargs
        self.logger = get_logger(f"provider.{self.__class__.__name__}")
    
    @abstractmethod
    def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 30,
        **kwargs
    ) -> 'ProviderResponse':
        """
        调用LLM生成文本
        
        Args:
            prompt: 输入提示
            temperature: 采样温度 (0.0-2.0)
            max_tokens: 最大生成tokens
            timeout: 超时时间（秒）
            **kwargs: Provider特定参数
            
        Returns:
            ProviderResponse: 统一的响应格式
            
        Raises:
            ProviderAPIError: API调用失败
            ProviderTimeoutError: 请求超时
            ProviderRateLimitError: 速率限制
        """
        pass
    
    @abstractmethod
    def validate_credentials(self) -> bool:
        """
        验证API凭证是否有效
        
        Returns:
            bool: 凭证是否有效
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Provider名称
        
        Returns:
            str: Provider标识符，如 "openai", "anthropic"
        """
        pass


class ProviderResponse(BaseModel):
    """Provider响应的统一格式"""
    
    text: str = Field(..., description="生成的文本")
    model: str = Field(..., description="使用的模型")
    usage: TokenUsage = Field(..., description="Token使用量")
    finish_reason: Optional[str] = Field(None, description="结束原因")
    raw_response: Optional[Dict[str, Any]] = Field(
        None,
        description="原始响应（用于调试）"
    )


# Provider异常类
class ProviderError(Exception):
    """Provider错误基类"""
    pass


class ProviderAPIError(ProviderError):
    """API调用错误"""
    pass


class ProviderTimeoutError(ProviderError):
    """请求超时"""
    pass


class ProviderRateLimitError(ProviderError):
    """速率限制"""
    pass


class ProviderAuthenticationError(ProviderError):
    """认证失败"""
    pass
```

---

### 3.2 LLMClient接口

```python
from typing import Optional
import time

class LLMClient:
    """
    LLM客户端
    
    封装多Provider调用，提供统一接口和重试机制。
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化LLM客户端
        
        Args:
            config: LLM配置
        """
        self.config = config
        self.provider = self._init_provider(config.provider)
        self.logger = get_logger("llm_client")
    
    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        生成代码（带重试）
        
        Args:
            prompt: 输入提示
            temperature: 温度（覆盖配置）
            max_tokens: 最大tokens（覆盖配置）
            **kwargs: 额外参数
            
        Returns:
            LLMResponse: 统一响应格式
            
        Raises:
            LLMClientError: 客户端错误
        """
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens
        
        # 重试逻辑
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                provider_response = self.provider.complete(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.config.timeout,
                    **kwargs
                )
                
                return LLMResponse(
                    text=provider_response.text,
                    usage=provider_response.usage,
                    model=provider_response.model,
                    finish_reason=provider_response.finish_reason
                )
            
            except ProviderRateLimitError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # 指数退避
                    self.logger.warning(
                        f"Rate limit hit (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)
                else:
                    raise LLMClientError(f"Rate limit exceeded after {max_retries} retries") from e
            
            except ProviderTimeoutError as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Timeout (attempt {attempt + 1}/{max_retries}), retrying"
                    )
                    time.sleep(base_delay)
                else:
                    raise LLMClientError(f"Timeout after {max_retries} retries") from e
            
            except ProviderAuthenticationError as e:
                # 认证错误不重试
                raise LLMClientError(f"Authentication failed: {e}") from e
            
            except ProviderAPIError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    self.logger.warning(
                        f"API error (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    raise LLMClientError(f"API error after {max_retries} retries: {e}") from e
    
    def _init_provider(self, provider_name: str) -> BaseProvider:
        """
        初始化Provider
        
        Args:
            provider_name: Provider名称
            
        Returns:
            BaseProvider: Provider实例
            
        Raises:
            ValueError: 不支持的Provider
        """
        if provider_name == "openai":
            from .providers.openai_provider import OpenAIProvider
            return OpenAIProvider(
                api_key=self.config.api_key,
                model=self.config.model
            )
        
        elif provider_name == "anthropic":
            from .providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(
                api_key=self.config.api_key,
                model=self.config.model
            )
        
        elif provider_name == "local":
            from .providers.local_provider import LocalProvider
            return LocalProvider(
                base_url=self.config.base_url,
                model=self.config.model
            )
        
        else:
            raise ValueError(
                f"Unsupported provider: {provider_name}. "
                f"Supported: openai, anthropic, local"
            )


class LLMClientError(Exception):
    """LLM客户端错误"""
    pass
```

---

## 4. Sandbox Executor接口

### 4.1 SandboxExecutor接口

```python
from typing import Dict, Any, Callable
import multiprocessing
import time

class SandboxExecutor:
    """
    沙箱执行器
    
    在隔离环境中安全执行Python代码，运行测试用例。
    """
    
    def __init__(self, config: SandboxConfig):
        """
        初始化沙箱执行器
        
        Args:
            config: 沙箱配置
        """
        self.config = config
        self.logger = get_logger("sandbox_executor")
    
    def execute(
        self,
        code: str,
        test_cases: List[TestCase],
        function_name: str = "solution"
    ) -> SandboxResult:
        """
        执行代码并运行所有测试用例
        
        Args:
            code: Python代码
            test_cases: 测试用例列表
            function_name: 要调用的函数名（默认"solution"）
            
        Returns:
            SandboxResult: 执行结果
        """
        # 1. 编译检查
        try:
            from RestrictedPython import compile_restricted
            compiled_code = compile_restricted(
                code,
                filename='<generated>',
                mode='exec'
            )
        except SyntaxError as e:
            return SandboxResult(
                status="syntax_error",
                error_message=f"Syntax error: {e}",
                test_results=[],
                execution_time=0,
                all_passed=False
            )
        
        # 2. 运行测试用例
        test_results = []
        total_time = 0.0
        
        for i, test_case in enumerate(test_cases):
            result = self._run_single_test(
                compiled_code,
                test_case,
                i,
                function_name
            )
            test_results.append(result)
            total_time += result.execution_time
            
            # 严重错误时停止后续测试
            if result.status in ["timeout", "memory_error"]:
                break
        
        # 3. 判断整体状态
        all_passed = all(tc.passed for tc in test_results)
        
        if all_passed:
            status = "success"
        elif any(tc.status == "timeout" for tc in test_results):
            status = "timeout"
        elif any(tc.status == "memory_error" for tc in test_results):
            status = "memory_error"
        elif any(tc.status == "runtime_error" for tc in test_results):
            status = "runtime_error"
        else:
            status = "failed"
        
        return SandboxResult(
            status=status,
            test_results=test_results,
            execution_time=total_time,
            all_passed=all_passed
        )
    
    def _run_single_test(
        self,
        compiled_code,
        test_case: TestCase,
        index: int,
        function_name: str
    ) -> TestCaseResult:
        """
        运行单个测试用例（在独立进程中）
        
        Args:
            compiled_code: 编译后的代码
            test_case: 测试用例
            index: 测试用例索引
            function_name: 函数名
            
        Returns:
            TestCaseResult: 测试结果
        """
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=self._execute_in_process,
            args=(compiled_code, test_case, function_name, queue)
        )
        
        start_time = time.time()
        process.start()
        process.join(timeout=self.config.timeout_seconds)
        execution_time = time.time() - start_time
        
        # 超时处理
        if process.is_alive():
            process.terminate()
            process.join()
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                status="timeout",
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=f"Execution timeout ({self.config.timeout_seconds}s)",
                execution_time=execution_time
            )
        
        # 获取结果
        if not queue.empty():
            result_data = queue.get()
            
            if result_data['success']:
                actual = result_data['output']
                expected = test_case.expected_output
                passed = self._compare_outputs(actual, expected)
                
                return TestCaseResult(
                    test_case_index=index,
                    passed=passed,
                    status="passed" if passed else "wrong_answer",
                    actual_output=actual,
                    expected_output=expected,
                    error_message=None if passed else "Output mismatch",
                    execution_time=execution_time
                )
            else:
                return TestCaseResult(
                    test_case_index=index,
                    passed=False,
                    status="runtime_error",
                    actual_output=None,
                    expected_output=test_case.expected_output,
                    error_message=result_data['error'],
                    execution_time=execution_time
                )
        
        return TestCaseResult(
            test_case_index=index,
            passed=False,
            status="unknown_error",
            actual_output=None,
            expected_output=test_case.expected_output,
            error_message="Process terminated without result",
            execution_time=execution_time
        )
    
    def _execute_in_process(
        self,
        compiled_code,
        test_case: TestCase,
        function_name: str,
        result_queue: multiprocessing.Queue
    ):
        """
        在独立进程中执行代码（内部方法）
        
        Args:
            compiled_code: 编译后的代码
            test_case: 测试用例
            function_name: 函数名
            result_queue: 结果队列
        """
        try:
            # 创建安全的全局命名空间
            safe_globals = self._create_safe_globals()
            
            # 执行代码
            exec(compiled_code, safe_globals)
            
            # 获取solution函数
            if function_name not in safe_globals:
                result_queue.put({
                    'success': False,
                    'error': f"Function '{function_name}' not defined"
                })
                return
            
            solution_func = safe_globals[function_name]
            
            # 调用函数
            output = solution_func(**test_case.input)
            
            result_queue.put({
                'success': True,
                'output': output
            })
        
        except Exception as e:
            result_queue.put({
                'success': False,
                'error': f"{type(e).__name__}: {str(e)}"
            })
    
    def _create_safe_globals(self) -> Dict[str, Any]:
        """
        创建安全的全局命名空间
        
        Returns:
            Dict: 受限的全局命名空间
        """
        from RestrictedPython import safe_builtins, limited_builtins
        
        safe_globals = {
            '__builtins__': {
                # 基础函数
                'len': len, 'range': range, 'enumerate': enumerate,
                'zip': zip, 'map': map, 'filter': filter,
                'sorted': sorted, 'sum': sum, 'min': min, 'max': max,
                'abs': abs, 'pow': pow, 'round': round,
                # 类型
                'int': int, 'float': float, 'str': str, 'bool': bool,
                'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
                # 其他
                'print': print,  # 允许打印（调试用）
            },
            '__import__': self._restricted_import,
        }
        
        return safe_globals
    
    def _restricted_import(self, name, *args, **kwargs):
        """
        限制模块导入
        
        Args:
            name: 模块名
            
        Returns:
            模块对象
            
        Raises:
            ImportError: 模块不在白名单中
        """
        if name not in self.config.allowed_imports:
            raise ImportError(
                f"Import of '{name}' is not allowed. "
                f"Allowed modules: {self.config.allowed_imports}"
            )
        
        return __import__(name, *args, **kwargs)
    
    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """
        比较输出（支持多种类型）
        
        Args:
            actual: 实际输出
            expected: 预期输出
            
        Returns:
            bool: 是否匹配
        """
        # 类型不匹配
        if type(actual) != type(expected):
            return False
        
        # 浮点数比较（允许误差）
        if isinstance(actual, float):
            return abs(actual - expected) < 1e-6
        
        # 列表/元组递归比较
        if isinstance(actual, (list, tuple)):
            if len(actual) != len(expected):
                return False
            return all(
                self._compare_outputs(a, e)
                for a, e in zip(actual, expected)
            )
        
        # 集合比较（无序）
        if isinstance(actual, set):
            return actual == expected
        
        # 其他类型直接比较
        return actual == expected
```

---

## 5. 数据加载接口

### 5.1 ProblemLoader接口

```python
from typing import List, Optional
import json

class ProblemLoader:
    """
    问题数据集加载器
    """
    
    def load(self, dataset_path: str) -> List[Problem]:
        """
        从JSON文件加载问题数据集
        
        Args:
            dataset_path: 数据集文件路径
            
        Returns:
            List[Problem]: 问题列表
            
        Raises:
            FileNotFoundError: 文件不存在
            JSONDecodeError: JSON格式错误
            ValidationError: 数据验证失败
        """
        pass
    
    def validate_dataset(self, data: List[Dict]) -> List[Problem]:
        """
        验证并转换数据集
        
        Args:
            data: 原始数据（字典列表）
            
        Returns:
            List[Problem]: 验证后的Problem对象列表
            
        Raises:
            ValidationError: 验证失败
        """
        pass
    
    def filter_problems(
        self,
        problems: List[Problem],
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Problem]:
        """
        过滤问题
        
        Args:
            problems: 问题列表
            difficulty: 难度筛选（可选）
            tags: 标签筛选（包含任一标签即可，可选）
            limit: 最大数量（可选）
            
        Returns:
            List[Problem]: 过滤后的问题列表
        """
        pass
```

---

## 6. 结果收集接口

### 6.1 ResultCollector接口

```python
from typing import List, Optional
import json
from pathlib import Path

class ResultCollector:
    """
    执行结果收集器
    """
    
    def __init__(self, output_dir: str):
        """
        初始化结果收集器
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.output_dir / "results.jsonl"
    
    def save(self, result: ExecutionResult):
        """
        保存单个结果（追加模式）
        
        Args:
            result: 执行结果
        """
        pass
    
    def save_batch(self, results: List[ExecutionResult]):
        """
        批量保存结果
        
        Args:
            results: 结果列表
        """
        pass
    
    def get_all_results(self) -> List[ExecutionResult]:
        """
        获取所有已保存的结果
        
        Returns:
            List[ExecutionResult]: 结果列表
        """
        pass
    
    def get_by_strategy(self, strategy_name: str) -> List[ExecutionResult]:
        """
        按策略查询结果
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            List[ExecutionResult]: 该策略的所有结果
        """
        pass
    
    def export_to_csv(self, output_path: str):
        """
        导出为CSV格式
        
        Args:
            output_path: CSV文件路径
        """
        pass
```

---

## 7. 指标计算接口

### 7.1 MetricsCalculator接口

```python
import numpy as np
from scipy import stats
from typing import Dict, List

class MetricsCalculator:
    """
    指标计算器
    """
    
    def calculate(
        self,
        results: List[ExecutionResult]
    ) -> Dict[str, StrategyMetrics]:
        """
        计算所有策略的指标
        
        Args:
            results: 执行结果列表
            
        Returns:
            Dict[str, StrategyMetrics]: 策略名称 -> 指标
        """
        pass
    
    def calculate_single_strategy(
        self,
        results: List[ExecutionResult],
        strategy_name: str
    ) -> StrategyMetrics:
        """
        计算单个策略的指标
        
        Args:
            results: 该策略的所有结果
            strategy_name: 策略名称
            
        Returns:
            StrategyMetrics: 指标对象
        """
        pass
    
    def compare_strategies(
        self,
        metrics: Dict[str, StrategyMetrics]
    ) -> List[ComparisonResult]:
        """
        策略两两对比分析
        
        Args:
            metrics: 各策略的指标
            
        Returns:
            List[ComparisonResult]: 对比结果列表
        """
        pass
```

---

## 8. 报告生成接口

### 8.1 ReportGenerator接口

```python
from typing import Dict, List
from pathlib import Path

class ReportGenerator:
    """
    报告生成器
    """
    
    def generate(
        self,
        metrics: Dict[str, StrategyMetrics],
        results: List[ExecutionResult],
        output_dir: str
    ) -> str:
        """
        生成完整报告
        
        Args:
            metrics: 各策略指标
            results: 所有执行结果
            output_dir: 输出目录
            
        Returns:
            str: 报告文件路径
        """
        pass
    
    def _generate_summary_table(
        self,
        metrics: Dict[str, StrategyMetrics]
    ) -> str:
        """
        生成汇总表格（Markdown）
        
        Args:
            metrics: 各策略指标
            
        Returns:
            str: Markdown表格
        """
        pass
    
    def _generate_charts(
        self,
        metrics: Dict[str, StrategyMetrics],
        output_dir: Path
    ):
        """
        生成图表
        
        Args:
            metrics: 各策略指标
            output_dir: 输出目录
        """
        pass
```

---

**文档版本**: v1.0  
**创建日期**: 2026-09-14  
**对应架构版本**: v1.0
