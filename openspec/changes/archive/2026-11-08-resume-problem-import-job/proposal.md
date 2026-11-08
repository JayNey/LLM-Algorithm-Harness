## Why

[GitHub #413](https://github.com/JayNey/LLM-Algorithm-Harness/issues/413) 记录了个人题库大文件导入的恢复问题。进度查询连续失败后，刷新或重新进入题库会丢失组件内的作业标识和提交锁，可能造成重复导入。导入成功后，来源计数也会停留在旧值。

## What Changes

- 按账号保留异步导入作业引用，支持手动重试、刷新和重新进入题库后查询原作业。
- 根据服务端作业状态维持提交锁并展示报告、失败或暂停状态。
- 成功导入后刷新题目列表和来源计数。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/problems-management` 增加异步导入恢复、账号隔离和成功后刷新场景。

## Impact

影响前端题库导入面板、题库元数据刷新和浏览器验收。
