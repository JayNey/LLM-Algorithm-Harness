# 设计：Codeforces 公开导入

导入器先调用 `problemset.problems`，按 contest、rating 和标签过滤，再按 contestId/index 稳定排序并抓取题面。HTTP 429、5xx 和网络错误使用有界指数退避；4xx 直接报告。题面解析使用标准库 HTMLParser，提取描述、输入/输出说明和 `<pre>` 样例。

题目 ID 为 `codeforces_<contestId>_<index>`；rating 映射为不超过 1400 的 easy、1500–2100 的 medium、2200 以上的 hard；Codeforces 标签映射为项目通用标签。题目使用 stdin/stdout 协议和 `main()` 入口。没有可靠样例或题面请求失败时设置 `needs_manual_completion` 并保留原因。

CLI 同时支持 `harness import codeforces ...` 和现有 `--source codeforces` 形式，最终交给公共导入流程完成 schema 校验、去重、预览、确认和原子写入。
