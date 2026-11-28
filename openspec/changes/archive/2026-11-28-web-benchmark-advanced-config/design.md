# Design

## Context

见 proposal.md。API 已持久化完整策略及筛选，BenchmarkExecutor 当前却把筛选覆盖成套件题数。共享实验组件已有高级字段、参数白名单与筛选序列化。

## Decisions

- 保留 strategies_text 名称入口，增加按策略名保存的字符串态覆盖配置，仅为当前所选名称生成对象；复用 StrategyAdvancedFields 和 ProblemFilterFields，补充迭代与温度输入。避免复制另一套高级控件或要求用户输入完整配置 JSON。
- 复用共享 StrategyConfig、ProblemFilters、ExperimentDraft 的策略及筛选草稿类型；复用 parseCustomParams 与 problemFilters；局部校验保持与共享模型的范围一致。空字段不发送，显式 0 温度与默认值保留。
- 执行器在构造临时数据集前调用已有 ProblemLoader.filter_problems，保留套件顺序；筛选完成后临时数据已包含最终题目，Harness 不再重复过滤。使用配置副本而非改写调用者配置，保证异常时清理。空交集明确报错。
- API、预算与检查点链路保持既有协议；mock 仅替换外部模型和沙箱，验证真实服务、执行器、策略和结果链路。

## Risks / Trade-offs

- 数量上限按套件顺序而非原始数据集顺序：界面明确说明；用顺序不同的数据集回归。
- 共享组件变动可能影响实验与 A/B：仅扩展可选 kind，跑共享及相关回归。
- 默认值继承可能因提前补默认而丢失：序列化省略空字段，测试显式默认与零温度。

## Verification

前端 payload/非法输入单测、浏览器 mock 表单与历史检查、后端离线创建到执行及结果测试、基准预算与任务回归、TypeScript 构建及修改文件格式检查。review_mode=off 如实记录，无付费模型调用。
