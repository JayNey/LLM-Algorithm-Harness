## 实施

- 两个 LiveCodeBench 示例内容相同，合并为一个使用 `--import-difficulty` 的本地预览命令。
- 通过 `llm_config.model` 配置模型。费用示例指定 `vanilla` 策略及输出目录，通过 `latest.json` 的 `latest_run` 定位 `summary.json`。
- 定价说明依据中央匹配逻辑及真实结果结构。汇总字段用于判断总费用是否完整，逐次调用的 trace 用于查看定价来源。
