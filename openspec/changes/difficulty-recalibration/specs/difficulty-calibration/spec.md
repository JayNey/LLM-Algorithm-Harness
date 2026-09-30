# difficulty-calibration Specification

## Purpose

基于历史评估数据自动重新标注题目难度：按题目聚合历史成功率，按可配置阈值（默认 >70% easy、30–70% medium、<30% hard）重标注，并生成前后对比的变更报告供人工复核。判定仅基于历史表现，无历史数据的题目保留原标注。

## ADDED Requirements

### Requirement: 难度重标注判定

系统 SHALL 支持从历史评估产物（`*_results.json`）按题目聚合成功率（status=success 且隐藏测试通过方计为通过）与平均迭代次数，并按阈值规则重标注难度：成功率 > easy 阈值（默认 0.7）→ easy，< hard 阈值（默认 0.3）→ hard，等于阈值的成功率归入 medium；阈值 SHALL 可自定义且必须满足 `0 <= hard < easy <= 1`；无历史记录的题目 SHALL 保留原难度。

#### Scenario: 按成功率重标注

- **WHEN** 某题在历史中出现多次且成功率为 25%
- **THEN** 该题被重标注为 hard，且成功率与平均迭代次数按全部记录聚合

#### Scenario: 边界与自定义阈值

- **WHEN** 以 `--easy-threshold 0.8 --hard-threshold 0.2` 重标注成功率分别为 0.81、0.8、0.19 的题目
- **THEN** 0.81 判为 easy（严格高于阈值），0.8 与 0.19 归入 medium 与 hard（等于阈值归 medium，严格低于判 hard）

#### Scenario: 无历史保留原标注

- **WHEN** 题库中某题在历史产物中没有任何记录
- **THEN** 该题保留原难度，并在报告中列为无历史数据

### Requirement: 重标注命令

系统 SHALL 提供 `harness recalibrate` 命令：`--history`（历史目录或单文件）与 `--output`（重标注题库 JSON 路径）必填，`--dataset`（默认 `data/problems.json`）、`--easy-threshold`、`--hard-threshold`、`--report`（Markdown 报告路径，缺省打印 stdout）可选；历史中无任何评估记录或参数非法时 SHALL 报错并以非零码退出；输出 SHALL 为完整题库 JSON 且不自动覆盖原题库文件。

#### Scenario: 生成重标注题库

- **WHEN** 以有效的历史目录与题库运行 `harness recalibrate`
- **THEN** `--output` 写出完整题库 JSON，其中难度字段为重标注结果，其余字段与原题库一致

#### Scenario: 无历史记录报错

- **WHEN** `--history` 指向的目录不包含任何可解析的评估记录
- **THEN** 命令报错并以非零码退出，不写出输出文件

### Requirement: 难度变更报告

重标注 SHALL 生成变更报告（`--report` 指定路径时写 Markdown 文件，否则打印 stdout），内容 SHALL 包含：重标注前后的难度分布对比、逐题变更明细（problem_id、原难度、新难度、成功率、平均迭代次数）、无历史数据题目的数量。

#### Scenario: 报告内容完整

- **WHEN** 重标注完成且存在难度变更与无历史题目
- **THEN** 报告呈现前后分布、每条变更含原难度/新难度/成功率/平均迭代，无历史题数如实统计
