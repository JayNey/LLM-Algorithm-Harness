# 治理版本完整数据与变更报告导出

## Why

Issue #529：现有个人主库导出不对应治理版本，版本详情又省略题面、测试与判题元数据。保存治理版本时没有持久化历史变更摘要，无法可靠地带走获批结果及其依据。

## What Changes

- 为选定治理版本提供完整数据集 JSON 下载，从所属用户的版本快照读取，保留所有 Problem 字段，可重新导入并创建评估。
- 在保存标签、难度治理版本的同一事务中持久化变更报告，记录题目 ID、原值、新值与批准项；报告不依赖后来主库或评估历史。
- 在版本详情提供数据集和变更报告下载，处理加载、失败、版本切换及会话切换。
- 对他人、不存在和已清理版本返回明确错误；旧版本或未记录治理摘要的版本仍可导出数据，但报告明确说明历史依据不可用。
- 保持个人主库 JSON/CSV 导出和用版本创建评估的既有行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/problems-management`：增加按用户与版本隔离的完整快照及可追溯标签/难度报告下载要求。

## Impact

- 后端：`api/files/governance.py`、`api/files/store.py`、`api/files/service.py`、`api/routes/evaluation_results.py`。新增版本下载 API 与兼容现有数据库的报告存储，不引入依赖。
- 前端：ProblemClient 接口、HTTP 客户端、治理版本详情、中英文文案。
- 验证：后端集成测试、前端客户端测试及本地 mock 浏览器验收，覆盖下载内容和请求参数，不调用付费模型。
- 预计 12 个交付文件（后端 4、前端 5、测试与验收脚本 3），另有本 change 的流程产物。虽然超过 tweak 的 6 文件提示值，仍限于 Issue #529 的单个 change；Open 批准后，在 Build 按 Runtime 范围复核记录用户是否同意继续 tweak。
