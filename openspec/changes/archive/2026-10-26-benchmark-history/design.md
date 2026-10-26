## Context

run_benchmark_command 已通过 BenchmarkExecutor 获得可 JSON 序列化的结果，但结尾只有历史存储 TODO。现有 BenchmarkHistoryStorage 已提供保存、加载和按模型/套件筛选；TrendAnalyzer 读取相同结构的策略准确率。

## Goals / Non-Goals

实现现有 benchmark 历史存储要求，保留现有 JSON 结构与默认 results/benchmark/ 目录。不新增查询命令、报告选项、数据库持久化或更改执行器的通用行为。

## Decisions

- 在 CLI 中导入 BenchmarkHistoryStorage，execute() 成功后用 suite.name、config.llm_config.model 和完整 results 调用 save_result。复用存储层生成的时间戳，不复制存储逻辑，也不把整个配置或 API 密钥写入文件。
- 保存完成后再输出评估完成摘要和实际保存路径。历史目录创建或写入异常交给现有命令异常处理，返回 1；评估失败或仅列出套件时不创建历史文件。
- 测试使用真实配置加载、套件加载、临时文件存储、历史筛选与趋势提取，只替换可能调用外部模型/执行沙箱的 executor.execute。

## Risks / Trade-offs

- 历史写入依赖目录权限和磁盘空间：用真实目录冲突与写入异常用例确认非零退出及错误提示。
- 现有存储按秒命名，同一模型同秒保存会覆盖；本次只接入现有模块，保持既有命名规则和存储接口。
