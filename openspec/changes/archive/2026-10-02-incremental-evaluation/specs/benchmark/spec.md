## MODIFIED Requirements

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
