# 提议：支持函数式与标准输入输出题目的执行和判题协议

## Problem

当前沙箱固定要求生成代码定义 `solution(**test_input)`，并把函数返回值写入标准输出解析。它无法直接运行 stdin/stdout 题目、LeetCode 的类方法入口，也无法区分调试输出和函数结果；比较逻辑还缺少题目级的精确、浮点容差和无序配置。

## Goal

- 按题目声明执行函数式、stdin/stdout 和简单 LeetCode 类方法入口。
- 为函数返回值建立独立于调试 stdout 的结果通道。
- 为 stdout 定义文本/JSON 解析和空白规则。
- 让比较器支持精确、递归浮点容差和显式无序列表比较。
- 对需要链表、树或交互协议的题目返回 `unsupported`，不归因于模型答错。

## Scope

- 扩展 `Problem`/`TestCase`/判题配置模型。
- 改造 host 和 Docker 执行路径及策略提示词。
- 保持旧版函数题和旧 `test_cases` 数据兼容。
- 增加执行、判题、提示词和不支持类型测试与文档。

## Non-goals

- 不实现通用链表/树序列化。
- 不实现交互题、多语言运行时或动态评测脚本。
- 不改变现有 Docker 隔离和资源限制策略。

## Impact

- 影响 `src/models.py`、`src/sandbox_executor.py`、策略提示词和 README。
- 旧函数题默认仍使用 `solution(**test_input)` 和兼容的浮点容差。
