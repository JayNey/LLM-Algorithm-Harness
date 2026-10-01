# problem-import Specification

## Purpose
TBD - created by archiving change problem-deduplication. Update Purpose after archive.

## Requirements

### Requirement: 提供 deduplicate 子命令

CLI SHALL 提供 `problems deduplicate` 子命令，支持以下参数：
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

#### Scenario: 预览去重结果

- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json --dry-run`
- **THEN** 系统仅输出重复题目列表，不修改数据集文件

#### Scenario: 自定义相似度阈值

- **WHEN** 用户运行 `harness problems deduplicate --threshold 0.85`
- **THEN** 系统使用 0.85 作为相似度阈值进行去重检测
