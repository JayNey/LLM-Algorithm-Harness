## Why

[#378](https://github.com/JayNey/LLM-Algorithm-Harness/issues/378) 记录了 README 中会被 CLI 拒绝的参数，以及与现行成本行为不一致的定价说明。

## What Changes

- 修正 LiveCodeBench 本地缓存导入示例。
- 使用 `--config` 选择模型，通过 `latest.json` 找到本次运行的费用汇总。
- 说明模型定价优先级、已知零价和未知费用，并区分汇总与逐次调用字段。

## Capabilities

### New Capabilities

### Modified Capabilities

## Impact

仅修改 README 中的用法和示例。使用本地夹具验证 CLI 与费用元数据。
