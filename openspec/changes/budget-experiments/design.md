# 设计：固定预算实验

## Execution

`ExperimentConfig` 描述题集、模型列表、策略列表、重复次数、沙箱和每题预算。运行器使用已有 TaskService 创建包含模型、策略、题目和重复编号的单元，复用现有策略与 Harness 的可见/隐藏测试边界。任务 JSON 支持中断恢复；配置和题集哈希不匹配时拒绝恢复。

## Budget

每个单元独享 `BudgetedLLMClient`，在调用前检查次数、已知 Token 和已过时间。未知 usage 会阻止严格 Token 预算下的新调用。单次 API 请求的输入和推理用量只有响应后可知，因此 Token/时间上限是调用前门控加响应后记录超额；报告必须披露该边界。通常供应商推理 token 是输出 token 的子集；若报告值超出输出 token，则预算按较大值计入，无法分配的价格保持未知。

## Accounting and reports

每模型显式价格以每千 Token 的输入/输出 USD 单价、来源和日期配置。任一调用用量未知或价格缺失时，该单元成本为 unknown；汇总有未知成本时也为 unknown。报告分别统计公开样例通过与独立隐藏测试通过，失败类型、修复率及按难度/标签的样本数、Token、时间。重复运行展示正式通过率范围与随机性说明。输出 `report.json`、`results.csv`、`report.md`。
