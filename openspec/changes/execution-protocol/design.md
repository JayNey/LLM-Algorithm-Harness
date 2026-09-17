# 设计：执行与判题协议

## Decisions

1. **题目级判题配置。** 新增 `JudgeConfig`，用 `comparison`（`exact`、`float_tolerance`、`unordered`）、`float_tolerance`、`whitespace`（`exact`、`trim`、`tokens`）和 `output_format`（`auto`、`text`、`json`）声明规则；默认值保持旧题兼容。
2. **函数结果走独立通道。** host 和 Docker wrapper 在执行候选代码前保存可信的 JSON 序列化器、写入函数和 stderr 文件描述符，并在独立用户命名空间中运行代码；返回值以每次运行唯一的 JSON 前缀写入 stderr，stdout 可用于调试，解析器兼容旧的纯 JSON stdout runner。
3. **stdin/stdout 使用原始输入。** 字符串输入原样写入 stdin，非字符串输入序列化为 JSON 加换行；文本输出按题目声明的空白策略比较，JSON 输出才进入 JSON 解析。
4. **入口适配范围收敛。** 默认入口调用 `solution(**test_input)`；形如 `Solution.method(...)` 的入口调用新建实例的方法。其余复杂入口或填写 `unsupported_reason` 的题目返回结构化 `unsupported`。
5. **递归比较而非全局排序。** 浮点容差递归处理嵌套列表、元组和字典；无序模式采用逐项匹配，仅对明确配置的列表忽略顺序，保留顺序敏感题的严格比较。
6. **提示词随协议变化。** 函数题、方法题和 stdin/stdout 题分别收到对应代码契约和判题规则，避免模型继续生成错误的 `solution` 包装。

## Error handling

- 空阶段仍返回 `sandbox_error`，不使用 `all([])` 伪造成功。
- stdout JSON 解析失败返回 `runtime_error`。
- 不支持题型返回 `unsupported`，策略结果的 `failure_category` 为 `unsupported`。
- 函数返回通道缺失或格式错误返回 `runtime_error`。
