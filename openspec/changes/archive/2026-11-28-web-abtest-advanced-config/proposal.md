# Web A/B 高级策略配置与题目筛选

## Why

issue #527：A/B 创建表单只提交策略名称和迭代次数，无法表达 API 已支持的完整 StrategyConfig 与 problem_filters。需要让用户从 Web 配置高级参数和执行题目范围，并验证参数经过持久化后被真实 runner 与策略读取。

## What Changes

- 添加可选策略 temperature、max_tokens、system_prompt 和受支持 custom_params，复用实验页现有参数白名单与校验。
- 添加 difficulty、tags、problem_ids、limit 筛选，沿用标签任一匹配、条件交集、最后按数据集顺序截取的共享语义。
- 请求与响应类型保留高级配置，在创建页和详情展示配置与范围；省略字段兼容既有默认行为。
- 保留两个变体、基线、seed、并发，以及变体 system prompt 优先于策略默认 prompt 的现有行为。
- 非法输入就地反馈；创建失败保留草稿并允许修正重提，提交期间禁用配置与重复提交。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/abtest-management`：增加高级策略配置、题目筛选、配置回显及错误恢复要求。

## Impact

预计影响 10–14 个交付文件，涵盖 A/B 前端类型、请求转换、创建与详情页、共享实验高级字段的类型适配、国际化及前后端回归测试。仅复用当前 A/B API 与执行链路；若发现范围内的传递遗漏则局部修复，不新增端点、公共 schema 或调整实验分组算法。使用本地 mock 与小题库验证，不调用付费模型或启动真实 Eval。

流程采用 tweak，配置为 direct/direct/off；文件数超出默认六文件提示线，但需求、验收和风险保持单一 change 范围。
