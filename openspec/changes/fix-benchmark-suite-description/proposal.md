## Why

编辑套件并清空描述后仍会看到旧值，冻结套件也会显示无法保存的编辑表单。见 [#426](https://github.com/JayNey/LLM-Algorithm-Harness/issues/426)。

## What Changes

- PATCH 省略描述时保留原值，显式提交 `null` 时清空，提交文本时替换。
- 保存后从服务端重新读取详情。冻结套件的详情页隐藏编辑入口和表单，服务端继续拒绝修改。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/benchmark-management` — 明确描述更新语义及冻结套件的编辑限制。

## Impact

基准套件 PATCH 服务、详情页和回归验证。
