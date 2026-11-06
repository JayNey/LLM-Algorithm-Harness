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
系统必须（MUST）支持基于指定题目集的历史，在同一图表中对比多个模型的性能趋势。比较模式仅使用历史结果，必须跳过评估、模型请求和运行历史写入。

#### Scenario: 对比不同模型
- **GIVEN** 指定题目集至少有两个模型各自具有可用于绘图的历史准确率
- **WHEN** 执行 `harness benchmark --suite benchmark.json --compare`
- **THEN** 生成包含这些模型趋势的报告，并且仅纳入指定题目集的数据

#### Scenario: 缺少可比较历史
- **WHEN** 指定题目集缺少历史，或具有可绘制准确率的模型不足两个
- **THEN** 命令分别提示缺少历史或可比较数据不足，以非零状态退出

### Requirement: 学习曲线报告
系统必须（MUST）生成包含趋势图、统计分析和版本对比的完整报告。CLI 的 `--output` 仅用于比较模式。

#### Scenario: 生成完整报告
- **GIVEN** 指定题目集具有可比较历史
- **WHEN** 执行 `harness benchmark --suite benchmark.json --compare --output reports/learning_curve.md`
- **THEN** 指定位置生成 Markdown 报告，包含可解析的趋势图链接、模型统计和版本对比表格

#### Scenario: 报告输出失败
- **WHEN** 比较模式无法写入指定报告
- **THEN** 命令显示输出错误并以非零状态退出

#### Scenario: 普通评估指定报告输出
- **WHEN** 用户未启用 `--compare` 就指定 `--output`
- **THEN** 命令提示 `--output` 的适用模式，并在评估启动前以非零状态退出
