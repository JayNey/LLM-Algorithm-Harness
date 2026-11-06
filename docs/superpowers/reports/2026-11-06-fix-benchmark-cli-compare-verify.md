# Benchmark CLI 历史比较验证

结论为通过。变更 `fix-benchmark-cli-compare` 对应 [issue #376](https://github.com/JayNey/LLM-Algorithm-Harness/issues/376)，验证对象为提交 `4eea185`。

## 完整性

- OpenSpec 任务完成 1/1。两条增量需求及五个场景通过 `comet classic openspec -- validate fix-benchmark-cli-compare --strict`。
- 实现涉及 CLI、趋势分析、报告链接、CLI 测试和 README。完整性和一致性对照使用该 change 的精简设计。

## 正确性

- `run_benchmark_command` 在加载评估配置及创建执行器前分流比较模式。按 suite 名称筛选历史，至少需要两个模型具有有效准确率；历史缺失和数据不足分别返回退出码 1。
- 比较报告通过已有 `ReportGenerator` 生成。真实 CLI 冒烟检查在没有评估配置的临时目录中写入指定 Markdown，确认包含两个模型的数据、三个可解析的图表链接以及两份原有历史记录。
- 回归测试覆盖默认和自定义报告路径、其他 suite 隔离、无效准确率、输出错误、历史文件保护以及 `--output` 单独使用。九个用例在修复前均失败。修复后 CLI 与 Benchmark 测试合计 74 项通过，既有用例确认普通评估仍保存完整历史。
- Black、Ruff、Git diff 检查以及离线源码包和 wheel 构建均通过。

## 一致性

使用现有 suite 名称键、趋势分析器和 Markdown 报告格式，延续普通评估路径。README 与 CLI 帮助说明 `--output` 的适用模式。Tweak 配置使用 `review_mode: off`，因此跳过独立自动代码审查。

## 离线全量验证

在允许绑定本机回环端口的环境中，使用仓库版本约束内的 Anthropic 0.125.0 运行 `python3 -m pytest -m 'not online' --no-cov`，退出码 0，4,033 项通过、18 项跳过。

首轮沙箱限制导致 `test_full_model_ids_round_trip_over_http`、`test_full_model_id_auth_and_validation_over_http`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]` 和 `test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[ab]` 在绑定回环端口时出错。这四项均在最终全量运行中通过。

## 归档校验

归档守卫 6 项通过。合并后的 Benchmark 主规范通过常规校验。严格模式仍报告 5 项原有格式警告，基线中有 7 项，已更新的两条需求通过严格检查。
