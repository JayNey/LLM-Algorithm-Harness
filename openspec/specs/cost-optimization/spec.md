# cost-optimization Specification

## Purpose
基于已完成实验的 comparison.json 历史数据，提供性价比排名、三目标组合推荐与预算约束下的最优评估方案计算，帮助降低评估成本。推荐基于历史数据，不保证未来表现一致；优化使用启发式方法，不保证全局最优。

## Requirements

### Requirement: 性价比排名

系统 SHALL 基于实验的组合数据输出 (模型, 策略, 准确率, 成本, 性价比) 排名，性价比 = 通过题数 / 总成本；成本未知或为零的组合标注"未知"并排除出排名，不显示 $0。

#### Scenario: 排名按性价比降序

- **WHEN** 实验包含多个定价已知的组合
- **THEN** 排名表按性价比从高到低排列，数值与组合数据手算一致

#### Scenario: 成本未知排除

- **WHEN** 某组合定价未配置
- **THEN** 该组合标注"未知"且不出现在排名中

### Requirement: 三目标组合推荐

系统 SHALL 支持三种推荐目标：highest_accuracy（最高准确率）、best_value（最高性价比）、lowest_cost（满足最低准确率约束的最便宜组合），并给出推荐依据。

#### Scenario: 三种目标各自成立

- **WHEN** 对同一实验分别请求三种目标
- **THEN** highest_accuracy 返回准确率最高的组合；best_value 返回性价比最高的组合；lowest_cost 在满足 min_accuracy 的组合中返回最便宜者，若无组合达标则明确说明无满足约束的方案

### Requirement: 预算优化器

系统 SHALL 支持给定预算（与可选最低准确率）下按难度分层计算推荐方案：每个难度层从历史数据中选择单位成本通过数最高且该层准确率达标的组合，输出推荐配置、估算总成本、预期准确率与可覆盖题数；历史数据不足的难度层明确标注。

#### Scenario: 预算内生成推荐

- **WHEN** 输入预算与历史实验数据
- **THEN** 每个难度层给出 (模型, 策略) 推荐，估算总成本不超过预算，且各层推荐满足最低准确率约束

#### Scenario: 历史数据不足时标注

- **WHEN** 某难度层无历史数据
- **THEN** 该层标注"无历史数据"，不虚构推荐

### Requirement: 优化 CLI 与产物

系统 SHALL 提供 `harness optimize --experiment <dir> [--budget N] [--min-accuracy X] [--objective ...]` 子命令，在实验目录写入 `optimization.json` 与 `OPTIMIZATION.md` 并输出摘要；无有效 comparison.json 时报错退出。

#### Scenario: CLI 完整执行

- **WHEN** 对已完成实验运行 optimize
- **THEN** 实验目录新增 optimization.json 与 OPTIMIZATION.md，内容与 stdout 摘要一致

#### Scenario: 输入无效时报错

- **WHEN** --experiment 指向的目录缺少 comparison.json
- **THEN** 命令以非零退出码报错，不生成产物
