## Purpose

为题目记录来源和输入协议，并隔离公开样例、反馈测试与隐藏最终评分，保证旧题库可以安全迁移。

## ADDED Requirements

### Requirement: 题目 Schema 记录可追溯元数据
系统 SHALL 记录 schema 版本、来源平台/题号/URL/版本、输入输出模式、入口签名和每个测试用例的用途来源。

#### Scenario: 加载新格式题目
- **WHEN** 题目包含来源、入口协议和 public/feedback/hidden 测试列表
- **THEN** 系统保留这些字段并按用途加载

#### Scenario: 迁移旧格式题目
- **WHEN** 题目只有旧版 `test_cases`
- **THEN** 系统将其迁移为公开样例，记录迁移状态，不声明存在隐藏测试

### Requirement: 隐藏测试不得进入模型上下文
系统 MUST 为策略提供不含隐藏输入和答案的 prompt 视图；反馈上下文也不得包含隐藏测试标识或预期输出。

#### Scenario: 生成初始提示词
- **WHEN** 题目同时包含公开、反馈和隐藏测试
- **THEN** 提示词只包含允许公开的题面与测试，不包含隐藏输入/答案

#### Scenario: 多轮反馈
- **WHEN** 策略根据公开或反馈用例继续生成代码
- **THEN** 反馈文本不包含隐藏用例内容，隐藏测试不触发再次修正

#### Scenario: 自定义策略边界
- **WHEN** Harness 调用任意策略生成候选代码
- **THEN** 策略接收到的题目副本不包含 hidden 用例，隐藏执行器只在策略返回后由 Harness 调用

### Requirement: 正式评测独立运行隐藏测试
系统 SHALL 在策略停止并提交最终代码后单独运行隐藏测试；仅有公开样例的题目 MUST 标记为仅样例验证并从正式隐藏通过率分母排除。

#### Scenario: 样例通过隐藏失败
- **WHEN** 代码通过全部公开样例但隐藏用例失败
- **THEN** 最终评测结果失败，且隐藏结果不回流到候选修正流程

#### Scenario: 仅样例题目
- **WHEN** 题目没有独立隐藏评分用例
- **THEN** 报告标记仅样例验证，并显示正式可评测题数不包含该题

### Requirement: 缺失可选阶段不得伪造通过
系统 SHALL 允许题目缺少 public 或 feedback 列表，但执行器 MUST 将显式请求的空阶段标记为未配置错误；没有可见测试时，策略结果由独立隐藏评测决定。

#### Scenario: 仅隐藏测试
- **WHEN** 题目只有 hidden 用例且模型生成代码
- **THEN** 策略不因空 public 阶段失败，Harness 运行 hidden 用例并据此确定最终结果

#### Scenario: 仅反馈测试
- **WHEN** 题目没有 public 用例但包含 feedback 用例
- **THEN** 策略执行 feedback 阶段，反馈结果决定是否继续迭代

### Requirement: 导出报告保留评测边界
系统 SHALL 在 CSV、Markdown、HTML 和 CLI 报告中展示正式可评测题数、正式隐藏通过情况和仅样例题数。

#### Scenario: 混合题库导出
- **WHEN** 结果同时包含正式题和仅样例题
- **THEN** 四种报告都能分别显示正式评测分母、隐藏通过情况和仅样例题数量
