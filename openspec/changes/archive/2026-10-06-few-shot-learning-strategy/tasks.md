## 实现任务清单

### 阶段 1：核心实现

- [x] 创建 `src/strategies/similarity/` 目录和 `__init__.py`
- [x] 实现 `src/strategies/similarity/tag_based.py` 标签相似度计算
  - [x] 实现 Jaccard 相似度计算函数
  - [x] 实现标签集合预处理（归一化、去重）
  - [x] 添加相似度阈值过滤
- [x] 实现 `src/strategies/few_shot_learning.py` 主策略类
  - [x] 实现 `__init__` 方法（接收配置参数）
  - [x] 实现 `retrieve_similar` 方法（检索相似题目）
  - [x] 实现 `build_few_shot_prompt` 方法（构建 prompt）
  - [x] 实现 `execute` 方法（完整执行流程）
  - [x] 实现示例库加载逻辑（从评估结果读取）
- [x] 在 `src/harness.py` 的 `STRATEGY_MAP` 中注册新策略

### 阶段 2：测试覆盖

- [x] 创建 `tests/test_few_shot_learning.py`
  - [x] 测试标签相似度计算（正常情况、边界情况）
  - [x] 测试相似题目检索（有匹配、无匹配、阈值过滤）
  - [x] 测试 prompt 构建（不同示例数量）
  - [x] 测试完整执行流程（Mock LLM 响应）
  - [x] 测试配置参数验证
- [x] 确保测试覆盖率 >= 90%

### 阶段 3：配置和文档

- [x] 更新 `config.example.json` 添加 few_shot_learning 配置示例
- [x] 更新 `README.md` 策略说明章节
  - [x] 添加 Few-Shot Learning 策略描述
  - [x] 添加配置参数说明
  - [x] 添加使用场景说明
- [x] 在 README 的"策略说明"部分添加详细说明

### 阶段 4：集成验证

- [x] 运行 `pytest tests/test_few_shot_learning.py -v`
- [x] 运行 `pytest --cov=src/strategies tests/test_few_shot_learning.py`
- [x] 在至少 5 道题目上运行端到端测试（覆盖 easy/medium）
- [x] 验证与现有策略的兼容性
