# 设计：LiveCodeBench 导入器

## Decisions

1. **版本显式且默认固定。** `release_v6` 作为默认版本，允许显式选择 `release_v1` 到 `release_v6`；不使用滚动的 `release_latest`。
2. **只读安全格式。** 本地缓存支持 JSON/JSONL；URL 只下载静态 JSON/JSONL。官方数据中 JSON 字符串形式的 public/private 测试可以解析，base64/zlib/pickle 私有字段只记录为不可安全解码，不执行反序列化。
3. **协议映射。** `testtype=stdin` 映射到 `stdin_stdout`；`functional` 映射到函数协议。public 测试进入 `public_test_cases`，安全解析的 private 测试进入 `hidden_test_cases`。
4. **可复现筛选。** 导入器记录 release 版本、起止日期、难度、limit、题目 ID 列表和内容摘要 SHA-256。
5. **不支持题型显式记录。** 缺少入口、无法安全解码 private 测试或协议未知时保留可导入元数据并设置人工补全/不支持说明，不静默换版本或猜测数据。

## Upstream

数据结构依据 LiveCodeBench 官方仓库 `lcb_runner/benchmarks/code_generation.py`；上游版本和许可信息由导入报告记录，具体可再分发范围由缓存文件的许可决定。
