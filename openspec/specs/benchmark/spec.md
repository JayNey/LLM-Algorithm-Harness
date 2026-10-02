# benchmark Specification

## Purpose
提供基准题目集管理、定期评估调度、历史数据存储、趋势分析和学习曲线报告生成功能。

## Requirements

### Requirement: 基准题目集定义
系统必须支持定义固定的基准题目集，包含题目列表、名称、版本和 frozen 标记。

#### Scenario: 定义标准基准题目集
- **Given** 用户创建 `benchmark.json` 配置文件
- **When** 配置包含 name、problems 列表和 frozen=true
- **Then** 系统能够加载并识别该基准题目集

### Requirement: 手动评估触发
系统必须支持通过 CLI 命令手动触发基准评估，并可选地启用增量模式以复用历史结果。

#### Scenario: 运行基准评估
- **WHEN** 执行 `harness benchmark --suite standard`
- **THEN** 系统对该题目集执行完整评估并记录结果

#### Scenario: 运行增量基准评估
- **WHEN** 执行 `harness benchmark --suite standard --incremental`
- **THEN** 系统检测题目集变化，仅评估变化的题目，复用未变化题目的历史结果

#### Scenario: 增量模式提示检测结果
- **WHEN** 启用 `--incremental` 且检测到可复用历史
- **THEN** 系统在评估前输出未变化题目数、新增题目数、修改题目数

### Requirement: 历史结果存储
系统必须将每次评估结果存储为独立的 JSON 文件，包含时间戳、模型信息和详细结果，并在增量模式下维护运行历史索引。

#### Scenario: 保存评估历史
- **WHEN** 评估完成
- **THEN** 在 `results/benchmark/` 目录生成 `{timestamp}_{model-id}.json` 文件

#### Scenario: 保存增量运行索引
- **WHEN** 增量模式下评估完成
- **THEN** 系统在 `results/.incremental/history.json` 中追加运行记录，包含数据集指纹和结果路径

#### Scenario: 增量索引文件自动创建
- **WHEN** 首次启用增量模式且索引文件不存在
- **THEN** 系统自动创建空的历史索引结构

### Requirement: 时间序列趋势图
系统必须能够生成时间序列折线图，展示模型在基准题目集上的性能变化。

#### Scenario: 生成学习曲线图
- **Given** 存在多个历史评估结果
- **When** 请求生成趋势图
- **Then** 生成时间 × 准确率的折线图

### Requirement: 多模型对比
系统必须支持在同一图表中对比多个模型的性能趋势。

#### Scenario: 对比不同模型
- **Given** 存在 gpt-4 和 gpt-4-turbo 的历史数据
- **When** 执行 `harness benchmark --suite standard --compare`
- **Then** 生成包含两个模型趋势线的对比图

### Requirement: 学习曲线报告
系统必须生成包含趋势图、统计分析和版本对比的完整报告。

#### Scenario: 生成完整报告
- **Given** 存在历史数据
- **When** 请求生成报告
- **Then** 报告包含趋势图、性能增长率、版本对比表格
