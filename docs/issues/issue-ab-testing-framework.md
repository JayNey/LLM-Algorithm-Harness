# [功能] A/B 测试框架

## 背景与目标

当前策略的 prompt 设计依赖人工经验，缺少科学的对比验证。A/B 测试框架可对同一策略的不同 prompt 版本进行对照实验，通过统计检验识别显著性差异，帮助优化 prompt 工程。

- 分类：实验评测
- 建议优先级：P2（中等价值，需要统计学基础）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#7-ab-测试框架)

## 工作范围

### 1. Prompt 变体管理
- 支持为同一策略定义多个 prompt 变体
  - 变体 ID、描述、prompt 模板
  - 版本控制和变更记录
- 配置文件支持 `prompt_variants` 列表

### 2. 实验设计
- 随机分配题目到不同变体组
  - 确保样本均衡分布（相同难度、标签比例）
  - 支持分层随机化（按难度分组）
- 对照组设置（baseline prompt）

### 3. 统计分析
- 自动计算统计指标：
  - 准确率差异（Δ）
  - 置信区间（95% CI）
  - p-value（显著性水平）
- 使用统计检验：
  - 两样本 t 检验（连续指标）
  - 卡方检验（分类指标）
  - Fisher 精确检验（小样本）

### 4. 报告生成
- A/B 测试专用报告：
  - 变体对比表（准确率、成本、显著性）
  - 箱线图：性能分布对比
  - 分标签细分分析
  - Prompt 优化建议

## 验收标准

- [ ] 配置支持定义多个 prompt 变体
- [ ] 题目随机分配算法通过均衡性检验
- [ ] 统计分析模块计算正确（手工验证）
- [ ] 报告包含 p-value 和置信区间
- [ ] CLI 命令：`harness ab-test --config ab_config.json`
- [ ] 文档更新：A/B 测试设计指南

## 边界

- 仅支持两组对比（A vs B），不支持多变体同时测试
- 统计分析使用标准库（scipy），不自建统计引擎
- 不涉及贝叶斯检验或序贯分析

## 依赖与关联

- 前置：#15 [功能] 固定预算实验（复用实验框架）
- 关联：策略 prompt 优化（基于测试结果改进）
- 后续扩展：多臂老虎机（Multi-Armed Bandit）动态分配

## 技术要点

### 随机分配
```python
from sklearn.model_selection import train_test_split

def split_problems(problems, variants):
    # 按难度分层
    for difficulty in ['Easy', 'Medium', 'Hard']:
        subset = [p for p in problems if p.difficulty == difficulty]
        # 均匀分配到变体组
        groups = np.array_split(subset, len(variants))
```

### 统计检验
```python
from scipy import stats

# t 检验
t_stat, p_value = stats.ttest_ind(group_a_scores, group_b_scores)

# 置信区间
ci = stats.t.interval(0.95, len(group_a)-1, 
                      loc=mean, scale=sem)
```

## 预期收益

- 实现工作量：约 5-7 天
- 科学价值：系统化的 prompt 优化方法
- 用户价值：提升策略性能，降低调优成本
- 差异化：超越简单对比，提供统计保证
