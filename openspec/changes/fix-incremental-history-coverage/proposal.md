## Why

CLI 只检查历史结果是否非空。新增策略或历史结果缺项时，增量评估仍会缩小执行题集，导致报告和后续历史缺题。见 GitHub Issue #362。

## What Changes

- 缩小执行题集前，确认每个当前结果分组都对每道未变题有且只有一条历史结果。
- 覆盖不足时执行全量评估，并将完整结果写入新一轮历史。

## Capabilities

### New Capabilities

### Modified Capabilities

- `incremental-evaluation` 的历史复用准入涵盖当前结果分组和未变题的完整性。

## Impact

影响 CLI 增量准入、增量评估规范及端到端回归测试。
