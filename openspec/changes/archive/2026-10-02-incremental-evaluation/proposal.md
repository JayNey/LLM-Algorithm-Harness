## Why

当前系统在数据集新增或修改题目时，需要重新评估所有题目，浪费大量时间和成本。对于已经评估过的未变动题目，重复评估既增加了 LLM API 调用成本，也延长了评估周期。需要实现增量评估机制，仅对变化的题目进行评估，复用历史结果以提高效率。

## What Changes

- **数据集指纹计算**：引入数据集指纹机制（基于题目 ID 集合的 hash），用于检测数据集变化
- **历史运行记录**：保存每次运行的数据集指纹和评估结果，支持增量检测
- **增量检测引擎**：比对当前数据集与历史指纹，识别新增、修改、删除的题目
- **结果合并**：复用历史未变动题目的评估结果，合并新评估结果生成完整报告
- **CLI 集成**：添加 `--incremental` 选项到主评估命令，自动检测并提示可用的增量模式

## Capabilities

### New Capabilities

- `incremental-evaluation`: 增量评估能力，支持检测数据集变化、仅评估变化题目、合并历史结果

### Modified Capabilities

- `benchmark`: 基准评估需要支持增量模式，避免重复评估未变化的题目

## Impact

**受影响代码**：
- `src/harness.py`：主评估流程需要集成增量检测逻辑
- `src/main.py`：CLI 入口需要添加 `--incremental` 参数
- `src/problem_loader.py`：题目加载器需要支持过滤和增量模式
- 新增模块：`src/incremental.py`（增量评估核心逻辑）

**受影响 API**：
- `AlgorithmHarness.run()` 方法需要支持增量模式参数
- `ProblemLoader` 需要新增指纹计算和变化检测方法

**数据存储**：
- 需要持久化历史运行记录（数据集指纹 + 结果路径）
- 建议存储位置：`results/.incremental/` 目录，使用 JSON 格式

**依赖变化**：
- 无新增外部依赖，使用 Python 标准库的 `hashlib` 进行指纹计算
