## 修复任务清单

### 1. 修复温度参数硬编码

- [x] 1.1 修改 `src/strategies/self_consistency.py:86-97`，将硬编码的 `temperature=0.8` 改为从 `custom_params` 读取
  - 在 `execute()` 方法开始处添加：`temperature = self.config.custom_params.get("temperature", 0.8)`
  - 将 `llm_client.generate()` 调用中的 `temperature=0.8` 改为 `temperature=temperature`
  - 验证：代码中不再有硬编码的温度值

### 2. 导出策略类

- [x] 2.1 修改 `src/strategies/__init__.py`，导出所有策略类
  - 导入四个策略类：`VanillaStrategy`, `ChainOfThoughtStrategy`, `MultiRoundFeedbackStrategy`, `SelfConsistencyStrategy`
  - 添加 `__all__` 列表声明导出的类
  - 验证：可以通过 `from src.strategies import SelfConsistencyStrategy` 导入

### 3. 更新文档

- [x] 3.1 修改 `README.md` 中 Self-Consistency 的配置参数说明（约 line 100-102）
  - 将 "固定为 0.8" 改为 "默认 0.8，可配置"
  - 验证：文档描述准确

- [x] 3.2 更新 `README.md` 中的配置示例（约 line 239-249），添加 temperature 参数
  - 在 `custom_params` 中添加 `"temperature": 0.8` 示例
  - 验证：配置示例完整

### 4. 验证修复

- [x] 4.1 运行现有测试，确保修复没有破坏功能
  - 运行 `pytest tests/strategies/test_self_consistency_report.py -v`
  - 验证：所有测试通过（导入验证成功）

- [x] 4.2 验证 logger 重复初始化问题（should fix 级别，可选修复）
  - 如果时间允许，优化 `src/strategies/self_consistency.py:39, 49` 的 logger 初始化
  - 将两次 `get_logger()` 调用合并为一次
  - 注：此项为非阻塞性优化，留待后续 PR 处理
