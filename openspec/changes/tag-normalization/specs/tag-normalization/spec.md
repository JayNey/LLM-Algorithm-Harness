# Tag Normalization Specification

## Purpose

统一跨平台题库标签，并在不修改原始数据的前提下提供可审计的标签建议。

## ADDED Requirements

### Requirement: Canonical 标签映射

系统 MUST 从 YAML 映射加载 canonical 标签及其英文、中文和平台别名，并将同义标签归一化为同一个 canonical name。

#### Scenario: 多语言别名归一化

- **Given** 标签列表包含 `hash-table`、`hash_map` 和 `哈希表`
- **When** 执行标签归一化
- **Then** 三个标签都变为 `hash-table`，重复值只保留一次

### Requirement: 确定性标签推荐

系统 MUST 基于题目标题和描述中的配置关键词提供标签建议，并为每条建议返回置信度和命中关键词。

#### Scenario: 关键词推荐

- **Given** 题目描述包含 `binary search` 和 `sorted array`
- **When** 生成标签建议
- **Then** 建议至少包含 `binary-search`，且置信度达到默认阈值 0.8

### Requirement: 用户自定义映射

系统 MUST 接受用户提供的 YAML 映射，并在内置标签表上追加 aliases、keywords 或新的 canonical 标签。

#### Scenario: 添加项目标签

- **Given** 自定义 YAML 声明 `segment-tree`、`segment_tree` 和 `线段树`
- **When** 加载该 YAML 并归一化题库
- **Then** 两个别名都归一化为 `segment-tree`

### Requirement: 安全的标准化命令

系统 MUST 提供 `harness tags normalize --dataset PATH` 命令，默认生成预览报告且不修改输入文件；只有用户指定输出路径时才写入新文件。

#### Scenario: 预览不覆盖原题库

- **Given** 用户只提供 `--dataset data/problems.json`
- **When** 执行标签命令
- **Then** 输出包含逐题变更和建议的报告，原始 JSON 内容保持不变

### Requirement: 显式应用建议

系统 MUST 要求用户显式传入 `--apply-recommendations` 才把文本推荐标签加入输出题库，并保留报告中的建议来源。

#### Scenario: 用户确认后写入

- **Given** 用户检查预览后提供 `--output normalized.json --apply-recommendations`
- **When** 执行标签命令
- **Then** 新文件包含标准化标签和已确认建议，输入文件不被覆盖
