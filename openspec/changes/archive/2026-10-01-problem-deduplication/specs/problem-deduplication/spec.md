## Purpose

提供题目去重能力，通过相似度检测和指纹匹配识别重复题目，并支持交互式或自动化的合并操作。

## ADDED Requirements

### Requirement: 相似度检测

系统 SHALL 使用 TF-IDF 向量化和余弦相似度算法检测文本相似的题目。

#### Scenario: 检测高度相似题目
- **WHEN** 两个题目的标题和描述余弦相似度 > 0.9
- **THEN** 系统标记为疑似重复题目

#### Scenario: 不同题目不被误判
- **WHEN** 两个题目的余弦相似度 <= 0.9
- **THEN** 系统不标记为重复

### Requirement: 指纹匹配

系统 SHALL 基于 `source_platform + source_problem_id` 生成唯一指纹，检测完全相同的题目。

#### Scenario: 检测完全相同题目
- **WHEN** 两个题目具有相同的 `source_platform` 和 `source_problem_id`
- **THEN** 系统标记为完全重复题目

#### Scenario: 处理缺失来源信息
- **WHEN** 题目缺少 `source_platform` 或 `source_problem_id`
- **THEN** 系统跳过指纹匹配，仅依赖相似度检测

### Requirement: 去重命令

系统 SHALL 提供 `harness problems deduplicate` CLI 命令，支持以下参数：
- `--dataset <path>` — 数据集路径（默认：data/problems.json）
- `--threshold <float>` — 相似度阈值（默认：0.9）
- `--auto-merge` — 自动合并重复题目，不提示用户
- `--dry-run` — 仅显示重复题目，不执行合并

#### Scenario: 交互式去重
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json`
- **THEN** 系统显示所有重复题目对，并提示用户选择保留或合并

#### Scenario: 自动去重
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json --auto-merge`
- **THEN** 系统自动合并所有重复题目，保留第一个出现的版本

#### Scenario: 预览模式
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json --dry-run`
- **THEN** 系统仅输出重复题目列表，不修改数据集文件

### Requirement: 合并策略

系统 SHALL 在合并重复题目时保留更完整的题目信息。

#### Scenario: 合并时保留完整信息
- **WHEN** 两个重复题目被合并
- **THEN** 系统保留字段更完整的题目作为主版本，并合并标签、测试用例等列表字段

#### Scenario: 记录合并历史
- **WHEN** 题目被合并
- **THEN** 系统在保留的题目中添加 `merged_from` 字段，记录被合并题目的 ID

### Requirement: 去重报告

系统 SHALL 输出详细的去重报告，包括检测到的重复题目数量、合并操作数量和跳过的题目数量。

#### Scenario: 显示去重统计
- **WHEN** 去重命令执行完成
- **THEN** 系统输出报告，包含：
  - 扫描的题目总数
  - 通过相似度检测发现的重复对数
  - 通过指纹匹配发现的重复对数
  - 实际合并的题目数量
  - 用户跳过的题目数量

### Requirement: 单元测试覆盖

去重核心逻辑 SHALL 有完整的单元测试覆盖。

#### Scenario: 测试相似度计算
- **WHEN** 运行单元测试
- **THEN** 测试验证 TF-IDF 和余弦相似度计算的准确性

#### Scenario: 测试指纹生成
- **WHEN** 运行单元测试
- **THEN** 测试验证指纹生成和匹配逻辑的正确性

#### Scenario: 测试合并策略
- **WHEN** 运行单元测试
- **THEN** 测试验证合并逻辑保留完整信息并正确记录历史
