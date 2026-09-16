## Why

安装后的 `harness` 命令当前指向不存在的 `src.cli:cli`，而实际入口位于 `src.main`。同时，CLI 强制要求 `--dataset` 并无条件覆盖配置文件中的数据集和输出目录，且主入口没有复用已经支持 YAML 的配置加载工具，导致文档承诺与实际行为不一致。

## What Changes

- 修正安装脚本入口，使 `harness` 与 `python -m src.main` 使用同一套 CLI。
- 统一 JSON/YAML 配置加载，并明确优先级为：显式 CLI 参数 > 配置文件 > 默认值。
- 允许数据集路径仅由配置文件提供；只有显式参数才覆盖配置值。
- 校验非正 `--limit`、无有效策略及筛选后空题集，并接通难度和标签筛选参数。
- 更新最小配置与运行文档，并用真实命令入口测试关键行为。

## Capabilities

### New Capabilities

- `cli-configuration`: 定义可安装 CLI、配置格式、参数优先级、筛选参数及失败行为。

### Modified Capabilities

无。

## Impact

- 影响 `src/main.py`、配置工具、安装入口、CLI 测试和 README 使用说明。
- 保留现有 `python -m src.main`、`--output` 和本地 JSON 题库用法；不引入新的运行时服务或外部依赖。
