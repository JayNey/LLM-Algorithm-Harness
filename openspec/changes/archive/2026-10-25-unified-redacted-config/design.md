## Context

复用监控路由的 administrator 依赖及全局 no-store 中间件。AuthService、FileService、MonitorService 均保留了实际 settings；API 执行限制读取 api.config.settings。

## Decisions

在 api/monitoring/config.py 定义四组固定字段元组和提取函数，仅 getattr 白名单成员，不导出 model_dump 再过滤，不依赖字段名黑名单。四组仅包含数值、布尔、可空限额。路由从同一进程持有的对象提取配置；不实例化 Settings、不读取 config.json、不调用现有健康探针。scope 明示 API 进程，避免把示例模型目录或单个评估任务的参数当成全局配置。保留现有配置接口兼容性。

## Risks / Trade-offs

新增配置默认不可见，需要显式审核白名单。输出是进程加载值而非磁盘未来值；多进程部署需分别诊断。无需配置写入、热加载或前端变更。

## 用户决策

用户回复 ab：继续 tweak，创建新分支。分支 codex/tweak/20261025/unified-redacted-config，目标 main。新增接口的升级提示已获继续授权；预计五个实现/测试/文档文件，另有工作流产物。
