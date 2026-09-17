## Purpose

为函数式、标准输入输出和简单 LeetCode 方法题提供明确、可审计的执行与判题协议。

## ADDED Requirements

### Requirement: 按题目协议执行候选代码
系统 SHALL 根据 `input_output_mode` 和 `entry_point` 执行函数题、stdin/stdout 题及简单类方法题。

#### Scenario: 函数题
- **WHEN** 题目使用默认函数入口
- **THEN** 系统调用 `solution(**test_input)` 并返回结构化函数结果

#### Scenario: 自定义函数入口
- **WHEN** 题目入口形如 `solve(value)`
- **THEN** 系统调用名为 `solve` 的函数，并在提示词中使用同一入口名

#### Scenario: 标准输入输出题
- **WHEN** 题目声明 `stdin_stdout`
- **THEN** 系统把测试输入写入 stdin，运行完整 Python 程序并捕获 stdout

#### Scenario: LeetCode 类方法
- **WHEN** 入口形如 `Solution.method(...)`
- **THEN** 系统实例化 `Solution` 并调用对应方法

### Requirement: 函数结果与调试输出隔离
系统 MUST 使用独立结果通道解析函数返回值，函数向 stdout 打印调试信息不得破坏结果解析。

#### Scenario: 函数打印调试信息
- **WHEN** `solution` 在返回前向 stdout 打印调试文本
- **THEN** 判题仍只比较函数返回值

### Requirement: 输出比较规则可配置
系统 SHALL 支持精确比较、递归浮点容差和显式无序列表比较，不能默认对所有列表排序。

#### Scenario: 浮点嵌套结构
- **WHEN** 题目配置 `float_tolerance`
- **THEN** 嵌套列表、元组和字典中的数值按该容差比较

#### Scenario: 顺序敏感结果
- **WHEN** 题目使用 `exact` 且返回列表顺序不同
- **THEN** 判题失败

#### Scenario: 无序结果
- **WHEN** 题目明确使用 `unordered`
- **THEN** 列表作为多重集合比较，不要求排序输入值

### Requirement: stdin/stdout 空白与解析规则明确
系统 SHALL 支持 text/JSON 输出格式，并按 `whitespace` 配置处理首尾空白、内部空白和末尾换行。

#### Scenario: token 空白策略
- **WHEN** 文本输出配置 `tokens`
- **THEN** 连续空白和末尾换行不影响 token 比较

#### Scenario: JSON 格式错误
- **WHEN** 输出配置为 `json` 但程序输出非法 JSON
- **THEN** 该用例标记为 `runtime_error`，不标记为模型 wrong answer

### Requirement: 不支持题型显式拒绝
系统 SHALL 对链表、树、交互等需要未实现协议的题目返回 `unsupported` 并保留原因。

#### Scenario: 明确不支持
- **WHEN** 题目填写 `unsupported_reason`
- **THEN** Harness 跳过模型生成和候选代码执行并返回 `unsupported` 结果

### Requirement: 提示词反映入口协议
系统 SHALL 在策略提示词中说明函数、类方法或 stdin/stdout 的代码契约和判题规则。

#### Scenario: stdin/stdout 提示词
- **WHEN** 题目使用 `stdin_stdout`
- **THEN** 提示词要求生成完整 stdin/stdout 程序，不要求定义 `solution`
