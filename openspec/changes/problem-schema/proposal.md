## Why

当前 `Problem` 只有一个 `test_cases` 列表，策略提示词、反馈和最终评分共用同一批用例。模型可能看到正式评测答案，旧题库也无法区分样例验证与隐藏评分。

## What Changes

- 扩展题目 Schema，记录 schema 版本、来源平台/题号/URL/版本、输入输出模式、入口签名和测试用途。
- 将测试用例分为公开样例、可反馈测试和隐藏最终评测，并提供不含隐藏内容的提示词视图。
- 旧版 `test_cases` 自动迁移为公开样例，记录迁移状态，绝不推断为隐藏测试。
- 策略只接收公开内容；多轮反馈可显式运行反馈用例；策略结束后独立运行隐藏用例。
- 报告区分仅样例验证题和具备独立隐藏评分用例的题。

## Capabilities

### New Capabilities

- `problem-schema`: 定义题目元数据、测试用途分层、旧格式迁移和隐藏评测边界。

## Impact

- 影响 `src/models.py`、`src/problem_loader.py`、策略提示词、Harness 最终评测、报告统计和题库测试。
- 保留旧版 `problems.json` 与 `Problem(test_cases=...)` 的导入兼容性。
