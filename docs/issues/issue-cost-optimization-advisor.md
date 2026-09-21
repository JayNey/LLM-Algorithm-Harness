# [创新功能] 成本优化建议

## 背景与目标

当前系统只记录成本，不提供优化建议。成本优化建议功能可基于历史数据分析性价比，推荐最具成本效益的模型和策略组合，并在给定预算下自动计算最优评估方案，帮助用户降低评估成本。

- 分类：成本管理
- 建议优先级：P2（中等价值，实用性强）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#15-成本优化建议)

## 工作范围

### 1. 性价比分析
- 计算每个模型/策略组合的性价比：
  ```
  性价比 = 准确率 / 成本
  ```
- 生成排名表：
  | 模型 | 策略 | 准确率 | 成本 | 性价比 |
  |------|------|--------|------|--------|
  | GPT-4 | CoT | 85% | $2.50 | 0.34 |
  | Claude-3 | Vanilla | 78% | $1.20 | 0.65 |

### 2. 最优组合推荐
- 根据不同目标推荐配置：
  - **最高准确率**：不考虑成本，选择最准确的组合
  - **最佳性价比**：准确率和成本的平衡点
  - **最低成本**：满足最低准确率要求下的最便宜方案
- 按题目类型细分推荐：
  - Easy 题目：使用便宜模型（如 GPT-3.5）
  - Medium/Hard 题目：使用强模型（如 GPT-4）

### 3. 预算优化器
- 输入预算约束，自动计算最优方案：
  ```bash
  harness optimize --budget 50 --min-accuracy 0.7
  ```
- 优化目标：
  - 在预算内最大化题目覆盖率
  - 在预算内最大化准确率
- 输出推荐配置：
  ```json
  {
    "budget": 50,
    "recommended_config": {
      "easy": {"model": "gpt-3.5-turbo", "strategy": "vanilla"},
      "medium": {"model": "gpt-4", "strategy": "cot"},
      "hard": {"model": "claude-3-opus", "strategy": "multi_round"}
    },
    "estimated_cost": 48.50,
    "estimated_accuracy": 0.75,
    "coverage": 200
  }
  ```

### 4. 成本敏感策略选择器
- 根据题目难度动态选择策略：
  - 简单题目：Vanilla（低成本）
  - 中等题目：CoT（中等成本）
  - 困难题目：Multi-Round（高成本，高准确率）
- 实时监控成本，达到预算上限时自动降级策略

## 验收标准

- [ ] 性价比计算正确并生成排名表
- [ ] 推荐配置在 3 种目标下都合理
- [ ] 预算优化器正确计算最优方案
- [ ] 成本敏感策略选择器集成到评估流程
- [ ] CLI 命令支持优化功能
- [ ] 报告包含成本优化建议章节
- [ ] 文档更新：成本优化使用指南

## 边界

- 推荐基于历史数据，不保证未来表现一致
- 优化算法使用启发式方法，不保证全局最优
- 不涉及模型定价预测（使用当前定价）

## 依赖与关联

- 前置：#15 [功能] 固定预算实验（需要成本数据）
- 关联：模型对比分析（性价比对比）
- 关联：学习曲线追踪（长期成本趋势）

## 技术要点

### 性价比计算
```python
def calculate_cost_efficiency(results):
    efficiency = []
    for model in models:
        for strategy in strategies:
            subset = filter_results(results, model, strategy)
            accuracy = sum(r.passed for r in subset) / len(subset)
            cost = sum(r.cost for r in subset)
            efficiency.append({
                'model': model,
                'strategy': strategy,
                'accuracy': accuracy,
                'cost': cost,
                'efficiency': accuracy / cost if cost > 0 else 0
            })
    return sorted(efficiency, key=lambda x: x['efficiency'], reverse=True)
```

### 预算优化器（贪心算法）
```python
def optimize_budget(problems, budget, min_accuracy):
    # 按性价比排序题目-配置对
    configs = []
    for problem in problems:
        for model, strategy in all_combinations:
            expected_accuracy = predict_accuracy(problem, model, strategy)
            cost = estimate_cost(problem, model, strategy)
            configs.append({
                'problem': problem,
                'model': model,
                'strategy': strategy,
                'accuracy': expected_accuracy,
                'cost': cost,
                'efficiency': expected_accuracy / cost
            })
    
    configs.sort(key=lambda x: x['efficiency'], reverse=True)
    
    # 贪心选择
    selected = []
    total_cost = 0
    for cfg in configs:
        if total_cost + cfg['cost'] <= budget:
            selected.append(cfg)
            total_cost += cfg['cost']
    
    return selected
```

### 成本敏感策略选择
```python
class CostSensitiveStrategy:
    def select_strategy(self, problem, remaining_budget):
        if problem.difficulty == 'Easy':
            return 'vanilla'
        elif problem.difficulty == 'Medium':
            if remaining_budget > threshold_medium:
                return 'cot'
            else:
                return 'vanilla'
        else:  # Hard
            if remaining_budget > threshold_hard:
                return 'multi_round'
            else:
                return 'cot'
```

## 预期收益

- 实现工作量：约 6-8 天
- 成本节省：潜在节省 20-40% 评估成本
- 用户价值：预算有限时的最优决策
- 实用性：工业应用必需功能

## 扩展方向

1. **动态定价监控**：跟踪模型价格变化，自动更新推荐
2. **多目标优化**：同时考虑成本、准确率、速度
3. **强化学习**：基于历史数据学习最优策略选择
