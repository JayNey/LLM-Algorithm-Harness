# A/B 样本与正式统计验证

变更 `fix-ab-test-pass-statistics` 完成 2/2 项任务。实现提交为 `73ccc0d4` 和 `29881f7c`。

## 验收结果

- 在固定模型输出和 host 沙箱中，两个变体均通过公开用例、失败于隐藏用例。JSON、Markdown 和实际结果 API 均返回样本 100%、正式 0%。以同一 runner 产物在浏览器验证实际详情组件，基线和实验组分别显示样本 100.0%、正式 0.0%。
- 纯公开题的正式通过率和差值区间为空。另用两组分布不同的逐题结果核对两套通过率、区间、Fisher 和 Welch t 检验。全为同一结果或缺组时检验标为不可用，两组分别为常量时 Welch t 的 p 值为空。
- API 读取旧版 1.0 产物时用逐题标志重算并返回 1.1。新旧报告的响应一致，原文件字节不变。删除重算所需字段后，API 返回 400 和重新运行提示。

## 规格与设计核对

增量规格 `api/experiment-management` 的四个场景均有 runner、API 或浏览器验证。JSON 与 API 同时提供样本和正式检验，现有 `comparison.statistics` 继续提供样本检验。详情页读取 API 的两组通过率与区间，并展示样本检验。实现符合精简设计，Tweak 预设省略独立的 Superpowers Design Doc。当前变更的 `review_mode` 为 `off`，已按规格、设计和基线差异逐项复核。

## 自动检查

- A/B runner、worker、结果 API、检查点相关的 66 项 Python 测试通过。
- 前端 322 项测试与生产构建通过，Python wheel 构建通过。修改文件通过 Black、Ruff 和针对实现文件的 mypy 检查。OpenSpec 增量规格通过严格校验。
- 全仓 mypy 报告 `api/progress.py`、`api/files/parsing.py`、`api/services/cost_alert_service.py` 的 4 项问题，已在 `main` 基线复现同一组诊断。

## 全量离线回归

允许本机回环端口后，全量离线套件通过 4059 项，跳过 18 项。4 项 Anthropic 策略边界用例因宿主 SDK 1.5.0 使用 httpx2 在初始化阶段报错。项目约束为 `anthropic>=0.18.0,<1`，使用独立的 0.125.0 依赖目录重跑 `tests/test_strategy_provider_params.py`，12 项全部通过。
