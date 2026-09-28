# 设计：分层 Prompt A/B 测试

`ABTestConfig` 包含一个模型、一个策略和两个 `PromptVariant`。每个变体可以覆盖 system prompt、前缀和后缀。题目按 difficulty + sorted tags 分层，固定 seed 后在每层交替分配 baseline/treatment，保证每层数量差不超过一个。

运行器复用现有 `AlgorithmHarness._execute_problem`、Problem schema 和 Docker 沙箱。结果记录每道题的变体、样例/隐藏通过、失败类型、Token、耗时和轮数。分类指标使用 Fisher 精确检验或卡方检验，连续 0/1 成功分数使用 Welch t 检验；成功率差异提供 Wald 95% CI。所有统计结果保留分母，p-value 不被解释成因果证明。
