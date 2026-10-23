## 修复方案

统一使用 evaluation.model or "evaluation-run" 解析模型。成本拆分沿用现有聚合；优化报告将评估聚合键改为 (model, strategy)，输出键中的真实模型。相同模型与策略继续合并，不同模型的同名策略分开。

## 验证

通过 API 回归验证多个真实模型、相同组合合并、null/空模型回退，以及混合 benchmark 数据、用户和时间过滤。先运行失败测试记录 RED，再修改源码确认 GREEN；运行成本相关测试、格式检查和 Python 构建。
