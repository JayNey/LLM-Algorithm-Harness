# Proposal

## Why

完成 GitHub issue #528。基准运行表单仅发送策略名称，无法表达已有 StrategyConfig 的高级参数和题目过滤；执行器还会覆盖过滤条件，导致即使 API 收到条件也不生效。

## What Changes

- 保留原策略名称选择，为每个已选策略配置迭代、温度、Token、系统提示词和已有有效自定义参数；留空沿用现有默认与继承语义。
- 提供难度、标签、题目 ID、数量上限筛选，明确先按套件顺序选题，再取各筛选条件交集，最后截取数量。
- 修复执行器覆盖过滤条件，保证实际执行与结果题数一致，空交集明确报错。
- 使用离线 mock 覆盖表单请求、API 持久化、真实策略执行及结果历史，兼容旧名称流程。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/benchmark-management`：高级策略与筛选输入、默认语义和非法输入反馈。
- `benchmark`：固定套件与运行筛选共同生效，结果反映实际执行范围。

## Impact

复用已有实验高级配置组件、类型和参数白名单，不新增 API 或 schema，不改预算、冻结、历史及检查点协议。预计涉及 10–12 个交付文件（implementation、tests、config 中的翻译资源），均属于 #528；Comet 产物另计。实现采用 direct/direct/off。验证使用本地测试及受控浏览器 mock，不调用付费模型。
