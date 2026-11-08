# Web 评估运行标识验证

结论为通过。实现提交为 `fc0738ca`，OpenSpec 任务完成 1/1，增量规格中的结果查询要求及六个场景均有验证证据。

## 验收证据

- Chrome 从创建页启动评估，真实 FastAPI、SQLite 与 worker 任务体保存结果。硬刷新结果页后，实际下载 Markdown、HTML 和 CSV 文件，并看到按同一 `run_id` 请求的分析数据。供应商模型、沙箱及队列传输使用离线替身。
- 将已完成记录的 `run_id` 清空以模拟旧数据后，硬刷新仍获得相同标识。三个下载和分析均成功。第二个账号按评估 ID 和运行标识读取结果均收到 404，三个报告和分析也收到 404。
- 暂停的两单元评估只完成一个单元。Chrome 显示部分报告警告，CSV 只含已落库单元。后端集成测试还验证恢复执行后标识保持稳定。
- 现有 API 测试覆盖结果汇总与分页、按标签过滤和所有权。新增回归断言在修改前因标识为空失败，修改后通过。

## 检查结果

- 后端评估工作流、结果服务、HTTP API 和 worker 测试通过，共 122 项。
- 前端测试通过，共 322 项。前端生产构建、Python wheel 构建、改动文件的 Ruff 检查与格式检查、OpenSpec 严格校验通过。
- `mypy src/ --ignore-missing-imports` 在当前分支和基线 `32cfdd98` 上均报告相同的四处既有错误，分布在 `api/progress.py`、`api/files/parsing.py` 和 `api/services/cost_alert_service.py`。
- 实现符合精简设计，公开标识在 worker 提交运行状态时持久化。历史兼容在读取时生效，结果、报告、分析共享所有者过滤。Tweak 预设使用 change 内的设计文档，自动代码审查按 `review_mode: off` 跳过。
