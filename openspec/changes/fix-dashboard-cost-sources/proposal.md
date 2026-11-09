## Why

首页目前把通用费用汇总的总额当成累计调用费用，因此会计入实验与 A/B 的支出，与首页说明及规格不符。修复 GitHub #417，并明确费用未知时的展示。

## What Changes

- 首页只累计当前用户的评估与已完成基准运行的已知费用。
- 区分有效零值、含未知成本的汇总和可重试的读取失败。
- 通用费用接口及费用页继续提供全来源汇总。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell`：明确首页费用按来源统计与未知费用的验收场景。

## Impact

影响首页费用客户端、指标渲染与前端验收。复用现有 `GET /costs/summary` 响应结构。
