# 设计：可审计的标签映射与推荐

`TagManager` 从 `config/tag_mapping.yaml` 读取 canonical 标签、aliases 和 keywords。自定义 YAML 会在内置映射上合并；别名通过 Unicode 规范化、大小写折叠和下划线/空格转换后查找，未知标签保留为稳定的小写短横线形式。

推荐器只读取题目标题和描述，使用词边界匹配英文短语、子串匹配中文短语，并优先更具体的短语，避免 `segment tree` 同时误推荐泛化的 `tree`。每条建议包含标签、置信度、命中关键词和原因，默认阈值为 0.8。

CLI 默认只输出 JSON 预览，`--report` 可另存报告；只有同时提供 `--output` 和可选的 `--apply-recommendations` 才写入新的 JSON 题库，原始文件永远不被覆盖。报告包含未知标签、变更题目、建议数量、逐题前后标签和建议详情。
