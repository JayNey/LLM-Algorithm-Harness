## Why

LeetCode 105、106、133 和 138 的公开样例以 JSON 表示节点，而函数判题直接传入或序列化 JSON，导致正确解答在 CLI 和 Web 都可能执行失败。GitHub #479 要求同时验证节点结构及克隆题的深拷贝。

## What Changes

- 让这四道题在共享判题路径中按题面协议转换节点与结果，兼容既有公开导入记录。
- 识别 Python 签名中仍不支持的节点类型，为导入题记录不可评估原因。
- 增加固定正确、错误解答的 Host 与 Docker 回归，说明旧记录的处理方式。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `execution-protocol`：支持四道指定 LeetCode 题的节点判题及其不可评估诊断。

## Impact

影响 LeetCode 导入元数据、共享函数执行及回归测试。复用现有进程、容器和 JSON 结果通道。
