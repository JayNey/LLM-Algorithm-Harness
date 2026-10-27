## Why

CLI 基准评估结束后只输出摘要，历史保存入口仍是 TODO，导致已有历史查询和趋势分析无法使用 CLI 的实际运行结果。

## What Changes

- 在 CLI 基准评估成功后，调用现有 BenchmarkHistoryStorage 保存套件名、配置中的模型 ID、时间戳与完整结果。
- 使用现有默认目录 results/benchmark/，向用户输出保存路径；保存失败沿用命令的错误处理并返回非零状态。
- 增加真实文件保存、历史筛选及趋势提取兼容性测试，并覆盖评估或保存失败和仅列出套件的路径。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。现有 benchmark 规范的“历史结果存储”已要求每次评估保存 JSON，本次补齐 CLI 实现，不改变规范要求。

## Impact

修改 src/main.py 和 tests/test_cli_commands.py，复用 src/benchmark/history.py 和 src/benchmark/analysis.py；无新增依赖、接口或数据库结构变更。
