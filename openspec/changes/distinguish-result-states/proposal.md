## Why
Issue #227（T12）要求区分等待、部分、暂停、失败/取消、完整、缺失和空结果。main 的结果完整性只返回 partial/empty，结果权限错误仍可能保留任务缓存，states fixture 尚未实现。

## What Changes
- 扩充 ResultAvailability，分开展示任务原因、记录数、完整性和请求错误。
- 保留联合读取和单次终态补读；权限错误清除整个资源数据，补读仍不一致显示未确认并允许手动重试。
- 补齐客户端/观察器/浏览器矩阵和公开验证证据，关联 #227 提交 PR。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `frontend/evaluation-observer`: 联合结果读取的可用性、权限与终态收敛。

## Impact
前端 evaluation 类型、presentation、结果 loader、hook、结果页和测试/fixture。无后端、public API、schema、依赖或架构变动。前置 #224/#225/#226 已关闭；基线 be54ba8（最新 origin/main）。

## Workflow Decision
用户明确选择继续 tweak，接受超过 6 文件提示阈值；保持单一 change。
