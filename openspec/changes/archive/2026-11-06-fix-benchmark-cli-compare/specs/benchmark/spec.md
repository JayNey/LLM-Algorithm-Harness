## MODIFIED Requirements

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
