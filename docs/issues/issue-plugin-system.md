# [工程质量] 插件系统

## 背景与目标

当前系统的扩展需要直接修改源代码，不利于社区贡献和用户自定义。插件系统允许用户编写自定义策略、数据源导入器、评估指标计算器，通过插件机制动态加载，提升系统的可扩展性和灵活性。

- 分类：工程质量
- 建议优先级：P3（低优先级，架构复杂度高）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#18-插件系统)

## 工作范围

### 1. 插件接口规范
- 定义插件基类和生命周期：
  ```python
  class Plugin:
      name: str
      version: str
      
      def initialize(self, config: dict):
          """插件初始化"""
          pass
      
      def execute(self, context: dict) -> dict:
          """插件核心逻辑"""
          pass
      
      def cleanup(self):
          """插件清理"""
          pass
  ```

### 2. 自定义策略插件
- 策略插件接口：
  ```python
  class StrategyPlugin(Plugin, StrategyBase):
      def solve_problem(self, problem: Problem) -> Solution:
          """实现求解逻辑"""
          pass
  ```
- 用户实现示例：
  ```python
  # plugins/my_strategy.py
  class MyCustomStrategy(StrategyPlugin):
      name = "my_custom_strategy"
      version = "1.0.0"
      
      def solve_problem(self, problem):
          # 自定义策略逻辑
          code = self.generate_code(problem)
          return Solution(code=code)
  ```
- 配置文件引用：
  ```yaml
  strategies:
    - plugin: plugins/my_strategy.py
      class: MyCustomStrategy
  ```

### 3. 自定义数据源导入器
- 导入器插件接口：
  ```python
  class ImporterPlugin(Plugin):
      def fetch_problems(self, **filters) -> List[Problem]:
          """从数据源获取题目"""
          pass
      
      def convert_to_schema(self, raw_data) -> Problem:
          """转换为标准 schema"""
          pass
  ```
- 用户实现示例：
  ```python
  # plugins/custom_importer.py
  class MyImporter(ImporterPlugin):
      name = "my_platform_importer"
      
      def fetch_problems(self, **filters):
          # 从自定义平台获取题目
          data = requests.get("https://my-platform/api/problems")
          return [self.convert_to_schema(item) for item in data.json()]
  ```

### 4. 自定义评估指标
- 指标插件接口：
  ```python
  class MetricPlugin(Plugin):
      metric_name: str
      
      def calculate(self, results: List[Result]) -> float:
          """计算指标值"""
          pass
      
      def visualize(self, value: float) -> dict:
          """生成可视化数据"""
          pass
  ```
- 用户实现示例：
  ```python
  # plugins/custom_metric.py
  class CodeEfficiencyMetric(MetricPlugin):
      metric_name = "code_efficiency"
      
      def calculate(self, results):
          # 自定义指标：代码行数 / 复杂度
          return sum(r.lines_of_code / r.complexity for r in results)
  ```

### 5. 插件管理系统
- 插件发现和加载：
  ```bash
  # 列出已安装插件
  harness plugin list
  
  # 安装插件
  harness plugin install plugins/my_strategy.py
  
  # 启用/禁用插件
  harness plugin enable my_custom_strategy
  harness plugin disable my_custom_strategy
  
  # 插件信息
  harness plugin info my_custom_strategy
  ```
- 插件沙箱隔离（安全性）
- 插件依赖管理

## 验收标准

- [ ] 插件接口规范文档完整
- [ ] 三种插件类型（策略、导入器、指标）都能正常工作
- [ ] 插件动态加载机制正确
- [ ] 插件沙箱隔离有效
- [ ] CLI 插件管理命令正常工作
- [ ] 至少提供 2 个示例插件
- [ ] 文档更新：插件开发指南

## 边界

- 插件使用 Python 实现，不支持其他语言
- 沙箱隔离使用 Python 限制，不保证绝对安全
- 不实现插件市场或在线分发

## 依赖与关联

- 关联：所有扩展功能（策略、导入器、指标）
- 后续扩展：插件市场、版本管理、依赖解析

## 技术要点

### 插件动态加载
```python
import importlib.util
import inspect

def load_plugin(plugin_path, class_name):
    # 加载模块
    spec = importlib.util.spec_from_file_location("plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # 获取插件类
    plugin_class = getattr(module, class_name)
    
    # 验证接口
    if not issubclass(plugin_class, Plugin):
        raise ValueError(f"{class_name} must inherit from Plugin")
    
    # 实例化
    return plugin_class()
```

### 插件注册表
```python
class PluginRegistry:
    def __init__(self):
        self._plugins = {}
    
    def register(self, plugin: Plugin):
        self._plugins[plugin.name] = plugin
    
    def get(self, name: str) -> Plugin:
        return self._plugins.get(name)
    
    def list_all(self) -> List[Plugin]:
        return list(self._plugins.values())

# 全局注册表
registry = PluginRegistry()
```

### 插件沙箱
```python
import sys
import types

def sandbox_exec(code, allowed_modules):
    # 限制可导入的模块
    safe_builtins = {
        '__import__': safe_import(allowed_modules),
        'print': print,
        # ... 其他安全内置函数
    }
    
    # 执行代码
    exec(code, {'__builtins__': safe_builtins})

def safe_import(allowed_modules):
    def _import(name, *args, **kwargs):
        if name not in allowed_modules:
            raise ImportError(f"Module {name} is not allowed")
        return __import__(name, *args, **kwargs)
    return _import
```

### 插件配置
```yaml
# plugins.yaml
plugins:
  - name: my_custom_strategy
    path: plugins/my_strategy.py
    class: MyCustomStrategy
    enabled: true
    config:
      temperature: 0.8
      max_rounds: 5
```

## 预期收益

- 实现工作量：约 10-14 天
- 可扩展性：用户可自定义扩展，无需修改核心代码
- 社区生态：促进社区贡献和插件分享
- 灵活性：满足特殊需求的定制化

## 风险与挑战

1. **安全性**：插件可能包含恶意代码
2. **稳定性**：插件质量参差不齐，可能导致系统崩溃
3. **维护成本**：插件接口变更影响兼容性

## 建议

**延后实现**，理由：
- 架构复杂度高，影响核心稳定性
- 当前用户规模小，自定义需求不强烈
- 优先完善核心功能，再考虑扩展机制
