# [创新功能] 学习曲线追踪

## 背景与目标

当前评估都是独立进行的，无法跟踪模型性能的时间演变。学习曲线追踪功能可定期运行相同题目集，记录性能趋势，支持模型版本对比，帮助了解模型能力的发展和版本迭代的影响。

- 分类：长期分析
- 建议优先级：P2（中等价值，需要长期数据积累）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#14-学习曲线追踪)

## 工作范围

### 1. 基准题目集（Benchmark Suite）
- 定义标准基准题目集：
  - 覆盖所有难度和算法类型
  - 题目固定，不随时间变化
  - 推荐 50-100 道题目
- 配置文件：`benchmark.json`
  ```json
  {
    "name": "Standard Benchmark v1.0",
    "problems": ["leetcode_1", "leetcode_2", ...],
    "frozen": true
  }
  ```

### 2. 定期评估调度
- 支持定期运行基准评估：
  - 手动触发：`harness benchmark --suite standard`
  - 定时任务：每周/每月自动运行
- 记录评估时间戳和模型版本

### 3. 历史数据管理
- 存储历史评估结果：
  ```
  results/
    benchmark/
      2024-01-15_gpt-4.json
      2024-02-15_gpt-4.json
      2024-01-15_gpt-4-turbo.json
      2024-02-15_gpt-4-turbo.json
  ```
- 数据结构包含：
  - 评估时间戳
  - 模型标识和版本
  - 题目级别的详细结果
  - 整体统计指标

### 4. 趋势分析和可视化
- 生成学习曲线图：
  - **时间序列折线图**：时间 × 准确率
  - **多模型对比**：不同模型的趋势叠加
  - **版本对比**：同一模型不同版本的性能差异
- 统计分析：
  - 性能增长率（月度/季度）
  - 版本迭代带来的改进幅度
  - 性能稳定性（标准差）

### 5. 报告生成
- 学习曲线报告：
  - 趋势图可视化
  - 关键里程碑标注（版本更新点）
  - 性能预测（可选，简单线性外推）
  - 版本对比表格

## 验收标准

- [ ] 基准题目集定义并固化
- [ ] 支持定期运行基准评估
- [ ] 历史数据正确存储和索引
- [ ] 学习曲线图正确生成
- [ ] 版本对比功能正常工作
- [ ] CLI 命令：`harness benchmark --suite standard --compare`
- [ ] 文档更新：基准评估使用指南

## 边界

- 仅追踪指定基准题目集，不自动追踪所有评估
- 性能预测使用简单统计方法，不涉及机器学习模型
- 不自动订阅模型版本更新（需要手动配置新版本）

## 依赖与关联

- 前置：#15 [功能] 固定预算实验（复用评估框架）
- 关联：模型对比分析（版本对比是特殊的模型对比）
- 后续扩展：自动检测模型版本更新并触发评估

## 技术要点

### 基准题目集配置
```json
{
  "name": "Standard Benchmark v1.0",
  "version": "1.0",
  "created_at": "2024-01-01",
  "problems": [
    {"id": "leetcode_1", "difficulty": "Easy", "tags": ["array"]},
    {"id": "leetcode_2", "difficulty": "Medium", "tags": ["dp"]},
    // ...
  ],
  "frozen": true
}
```

### 历史数据查询
```python
def load_history(model_name, suite_name):
    pattern = f"results/benchmark/*_{model_name}.json"
    files = glob.glob(pattern)
    history = []
    for f in sorted(files):
        timestamp = extract_timestamp(f)
        data = json.load(open(f))
        history.append({
            'timestamp': timestamp,
            'accuracy': data['accuracy'],
            'model_version': data.get('model_version', 'unknown')
        })
    return history
```

### 趋势图生成
```python
import matplotlib.pyplot as plt
import pandas as pd

df = pd.DataFrame(history)
df['timestamp'] = pd.to_datetime(df['timestamp'])

plt.figure(figsize=(12, 6))
for model in models:
    model_df = df[df['model'] == model]
    plt.plot(model_df['timestamp'], 
             model_df['accuracy'], 
             marker='o', 
             label=model)

plt.xlabel('Time')
plt.ylabel('Accuracy (%)')
plt.title('Learning Curve - Model Performance Over Time')
plt.legend()
plt.grid(True)
plt.savefig('learning_curve.png')
```

### 版本对比
```python
def compare_versions(model_name, version1, version2):
    data1 = load_benchmark_result(model_name, version1)
    data2 = load_benchmark_result(model_name, version2)
    
    improvement = {
        'accuracy': data2['accuracy'] - data1['accuracy'],
        'cost': data2['cost'] - data1['cost'],
        'speed': data2['avg_time'] - data1['avg_time']
    }
    return improvement
```

## 预期收益

- 实现工作量：约 5-7 天
- 长期价值：持续追踪模型演进
- 研究价值：LLM 能力发展趋势研究
- 实用价值：版本选型决策依据

## 注意事项

1. **需要长期数据积累**：至少 3 个月数据才有意义
2. **题目集保持固定**：确保对比的公平性
3. **考虑模型 API 变化**：版本更新可能改变行为
