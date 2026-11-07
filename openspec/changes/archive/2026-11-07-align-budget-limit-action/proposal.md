## Why

[#392](https://github.com/JayNey/LLM-Algorithm-Harness/issues/392) 中，用户可清空预算超限动作，但 PATCH 省略该字段，后端保留原值，导致界面给出误导性的保存反馈。

## What Changes

- 超限动作只能选择暂停或降级模型。尚无预算配置时，表单提示新建预算的默认动作是暂停。
- 仅在主动切换超限动作时提交该字段。保存成功后以 API 响应回填。
- 通过真实浏览器和 API 核对保存、刷新与回读。

## Capabilities

### Modified Capabilities

- `frontend/budget-alerts` 的预算与预警管理。

## Impact

预算表单、双语文案和现有浏览器回归脚本。沿用既有 PATCH 契约和持久化模型。
