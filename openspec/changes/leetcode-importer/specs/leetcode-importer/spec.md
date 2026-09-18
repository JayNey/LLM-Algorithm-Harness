## Purpose

从 LeetCode 公开题目接口导入可追溯的题面、元数据和公开样例，并在信息不足时明确要求人工补全。

## ADDED Requirements

### Requirement: 接受 LeetCode URL 或 slug
系统 SHALL 接受 `https://leetcode.com/problems/<slug>/...` URL 或裸 slug，并拒绝不支持的主机。

#### Scenario: 合法 URL
- **WHEN** 用户传入 LeetCode 题目 URL
- **THEN** 导入器提取 slug 并请求对应公开题目数据

#### Scenario: 裸 slug
- **WHEN** 用户传入 `two-sum`
- **THEN** 导入器按同一题目查询处理

#### Scenario: 不支持域名
- **WHEN** 用户传入其他站点 URL
- **THEN** 导入器给出不支持来源提示且不发起请求

### Requirement: 保存题目来源和公开元数据
系统 SHALL 保存 LeetCode 题号、题目 URL、版本标识、标题、难度、标签、题面、约束和可识别入口。

#### Scenario: 普通 Python 题
- **WHEN** GraphQL 响应包含题面、标签和 Python snippet
- **THEN** 结果映射为 `source_platform=leetcode`、`input_output_mode=function` 的 Problem

### Requirement: 样例解析不得伪造
系统 MUST 只把可靠识别的输入/期望输出写入 public 样例；无法可靠解析时 MUST 标记人工补全。

#### Scenario: 题面没有可配对输出
- **WHEN** 响应只有 `exampleTestcases` 输入或样例格式不明确
- **THEN** 结果不生成虚假测试用例，并带有 `needs_manual_completion` 和说明

#### Scenario: 多种公开样例形态
- **WHEN** 题面包含代码块、HTML entity、公式和多个 Input/Output 区块
- **THEN** 清洗结果保留代码、公式、约束含义并逐样例生成精确字段

### Requirement: 网络失败可控
系统 SHALL 对超时、限流、认证限制、题目不存在、GraphQL errors 和页面结构变化返回结构化失败，并限制重试次数。

#### Scenario: 限流
- **WHEN** API 返回 429
- **THEN** 导入器有限退避后失败，不无限重试或绕过限制

### Requirement: 导入流程可预览和去重
系统 SHALL 复用现有 import CLI 的 preview、strict、skip/overwrite 和原子持久化能力。

#### Scenario: 重复题目预览
- **WHEN** 导入题目的 `(source_platform, source_problem_id)` 已存在
- **THEN** preview 显示 skip/overwrite 决策且不修改数据集
