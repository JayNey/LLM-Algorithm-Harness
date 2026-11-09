## Why

[#425](https://github.com/JayNey/LLM-Algorithm-Harness/issues/425) 中，个人资料和密钥管理页读取失败后需要整页刷新，基准运行表单也无法区分密钥读取失败和没有密钥。密钥写入成功后的列表回读失败会遮住操作结果。

## What Changes

- 三个读取入口分别展示加载、失败和空数据，并提供页面内重试。
- 添加、改名和删除密钥成功后立即确认操作结果。列表回读失败时保留该结果，重试只读取列表。
- 用现有会话和页面生命周期隔离迟到响应。

## Capabilities

### Modified Capabilities

- `frontend/user-profile` 提供资料读取重试和独立空态。
- `frontend/api-keys` 区分列表状态和写入结果。
- `frontend/benchmark-management` 区分运行表单的密钥读取状态。

## Impact

个人资料页、API 密钥管理页、基准套件详情运行表单及其中英文提示。
