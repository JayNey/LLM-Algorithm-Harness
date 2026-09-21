# [创新功能] 模型能力图谱

## 背景与目标

当前报告只展示整体准确率和按标签统计，缺少对模型能力的系统化分析。模型能力图谱通过多维度可视化，全面展现模型在不同算法类型、难度级别上的强弱，生成直观的能力雷达图和知识覆盖热力图。

- 分类：数据分析与可视化
- 建议优先级：P2（中等价值，创新性强）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#11-模型能力图谱)

## 工作范围

### 1. 能力雷达图
- 定义能力维度：
  - **算法设计**：正确识别问题类型和选择算法
  - **代码实现**：将算法转换为可执行代码
  - **调试能力**：根据反馈修复错误
  - **优化能力**：提升代码效率（时间/空间复杂度）
  - **边界处理**：处理边界情况和特殊输入
- 每个维度的评分方法：
  - 算法设计：首轮生成的算法思路正确率
  - 代码实现：首次通过样例测试的比例
  - 调试能力：多轮反馈后的修复成功率
  - 优化能力：代码复杂度与最优解的接近程度
  - 边界处理：边界测试用例通过率
- 生成雷达图可视化

### 2. 算法类型分析
- 按算法标签统计成功率：
  - 动态规划、贪心、图论、树、数组、字符串等
  - 计算每个类型的：
    - 总题数
    - 成功数
    - 成功率
    - 平均轮次
- 识别强项和弱项（成功率 > 80% vs < 40%）

### 3. 知识覆盖热力图
- 二维热力图：
  - **横轴**：算法类型（DP、贪心、图论等）
  - **纵轴**：难度级别（Easy、Medium、Hard）
  - **颜色深度**：成功率（0-100%）
- 交互式热力图（鼠标悬停显示详情）
- 空白区域标注"未覆盖"（该组合无题目）

### 4. 综合报告
- 能力评估摘要：
  - 总体能力评级（A/B/C/D）
  - 强项 Top 3 和弱项 Top 3
  - 建议训练方向
- 可视化集成到 HTML 报告

## 验收标准

- [ ] 能力雷达图正确生成并可视化
- [ ] 算法类型分析准确统计所有标签
- [ ] 知识覆盖热力图正确显示成功率分布
- [ ] HTML 报告新增"能力图谱"章节
- [ ] 可视化图表交互式（鼠标悬停显示详情）
- [ ] 文档更新：能力图谱解读指南

## 边界

- 能力维度基于启发式规则评分，不涉及机器学习模型
- 仅分析已评估的题目，不预测未评估题目的表现
- 可视化使用前端库（Plotly、ECharts），不自建图表引擎

## 依赖与关联

- 前置：#15 [功能] 固定预算实验（需要完整评估数据）
- 关联：代码质量评估（优化能力维度）
- 关联：模型对比分析（多模型能力图谱对比）

## 技术要点

### 能力维度评分
```python
def calculate_capability_scores(results):
    scores = {
        'algorithm_design': 0,
        'code_implementation': 0,
        'debugging': 0,
        'optimization': 0,
        'edge_cases': 0
    }
    
    for result in results:
        # 算法设计：首轮思路正确
        if result.rounds[0].passed_sample:
            scores['algorithm_design'] += 1
        
        # 调试能力：多轮修复成功
        if result.final_status == 'passed' and len(result.rounds) > 1:
            scores['debugging'] += 1
        
        # ... 其他维度评分
    
    return {k: v / len(results) for k, v in scores.items()}
```

### 热力图数据准备
```python
import pandas as pd

# 构造热力图数据
data = []
for tag in tags:
    for difficulty in ['Easy', 'Medium', 'Hard']:
        subset = [r for r in results 
                  if tag in r.problem.tags 
                  and r.problem.difficulty == difficulty]
        success_rate = sum(r.passed for r in subset) / len(subset)
        data.append({
            'Algorithm': tag,
            'Difficulty': difficulty,
            'Success Rate': success_rate
        })

df = pd.DataFrame(data)
heatmap = df.pivot(index='Difficulty', 
                   columns='Algorithm', 
                   values='Success Rate')
```

### 雷达图可视化
```python
import plotly.graph_objects as go

fig = go.Figure(data=go.Scatterpolar(
    r=list(scores.values()),
    theta=list(scores.keys()),
    fill='toself'
))
fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
    title="Model Capability Radar"
)
```

## 预期收益

- 实现工作量：约 6-8 天
- 用户价值：直观了解模型能力全景
- 研究价值：系统化分析 LLM 能力特征
- 差异化：创新性可视化，提升项目吸引力
