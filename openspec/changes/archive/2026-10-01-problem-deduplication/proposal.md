## Why

从不同来源导入题目时，可能存在重复题目，影响数据集质量和算法评估准确性。当前系统缺少题目去重机制，导致重复题目在数据集中累积。

## What Changes

- 新增题目去重功能模块，提供相似度检测和指纹匹配两种去重策略
- 实现 `harness problems deduplicate` CLI 命令，支持交互式和自动去重
- 基于 TF-IDF + 余弦相似度检测文本相似题目（阈值 > 0.9）
- 基于 `source_platform + source_problem_id` 生成唯一指纹，检测完全相同的题目
- 提供合并建议，支持用户选择保留或合并重复题目

## Capabilities

### New Capabilities

- `problem-deduplication`: 题目去重核心能力，包括相似度计算、指纹匹配、重复检测和合并建议

### Modified Capabilities

- `problem-import/cli-commands`: 新增 `deduplicate` 子命令，扩展现有 CLI 命令集

## Impact

**新增文件：**
- `src/harness/utils/deduplication.py` — 去重核心逻辑（相似度计算、指纹生成）
- `tests/test_deduplication.py` — 单元测试

**修改文件：**
- `src/harness/cli.py` — 添加 `problems deduplicate` 命令

**依赖变更：**
- 需要 `scikit-learn` 用于 TF-IDF 向量化和余弦相似度计算

**用户影响：**
- 用户可以主动对现有数据集执行去重操作
- 不影响现有的导入流程，作为独立工具提供
