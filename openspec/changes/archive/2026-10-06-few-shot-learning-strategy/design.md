## 设计概述

Few-Shot Learning 策略通过检索已解决的相似题目作为示例，构建包含示例的 prompt 来辅助 LLM 求解新问题。第一阶段使用基于标签重叠的相似度计算，实现简单且无需外部依赖。

## 核心组件

### 1. FewShotLearningStrategy 类
继承 `StrategyBase`，实现完整的 few-shot 求解流程：
- 初始化：接收配置参数（示例数量、相似度阈值、相似度计算方式）
- 执行流程：检索相似题目 → 构建 few-shot prompt → 生成代码 → 返回结果

### 2. 相似度计算模块
`src/strategies/similarity/tag_based.py`：
- 计算两个题目的标签 Jaccard 相似度
- 过滤低于阈值的候选题目
- 支持标签权重（可选）

### 3. 示例数据库
- 使用评估历史结果作为示例库
- 从已成功求解的题目中检索
- 优先使用高质量解答（通过所有测试）

## 数据流

```
新题目 → 提取标签 → 计算相似度 → 排序过滤 → Top-K 示例
       ↓
示例题目 + 解答 → 构建 Prompt → LLM 生成 → 代码输出
```

## Prompt 模板设计

```
You are an expert algorithm problem solver.

Example 1:
Problem: [题目标题]
Description: [题目描述]
Tags: [标签列表]
Solution:
[解答代码]

Example 2:
...

Now solve this problem:
Problem: [当前题目标题]
Description: [当前题目描述]
Tags: [当前标签列表]
Provide your solution in Python:
```

## 配置参数

```yaml
strategies:
  - name: few_shot_learning
    config:
      num_examples: 3              # 检索示例数量
      similarity_metric: tag_overlap  # 相似度计算方式
      min_similarity_score: 0.3    # 最低相似度阈值
      example_source: solved_problems  # 示例来源
```

## 实现约束

- 第一阶段仅实现标签相似度，不引入向量数据库
- 示例库从项目现有的评估结果中构建
- 保持与现有策略接口一致
- 测试覆盖率 >= 90%
