## Why

[#444](https://github.com/JayNey/LLM-Algorithm-Harness/issues/444) 要求在发布构建上实测真实会话、管理员边界和跨账号资源隔离。全局定价覆盖影响所有用户的费用和预算，写入权限已确认为管理员专有。

## What Changes

- 登录用户可读全局定价目录和历史，仅管理员可在界面追加定价或调用写入接口。
- 用同一隔离生产部署中的两名普通用户和一名管理员记录会话、权限、资源归属和密钥持久化的 UI 与 API 结果，并记录实际供应商覆盖层。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/cost-management` — 明确共享定价接口的认证与管理员写入权限。
- `frontend/pricing-management` — 明确目录、历史和追加操作的角色权限。

## Impact

全局定价写入接口对普通用户返回 403。现有真实评估验收脚本以普通账号核对共享目录中的预算单价。验收使用独立部署、测试账号与数据，证据使用脱敏标识。
