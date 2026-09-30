# Design: 基于模型表现的难度自动重标注

## 实现说明

### 统计与判定（src/difficulty_calibration.py）

- `collect_stats()`：复用推荐器的历史解析口径——遍历 `--history` 目录（或单文件）下所有 `*_results.json`（跳过 metadata/summary/comparison 等），按 `problem_id` 聚合：`total`（出现次数）、`solved`（status=success 且 hidden_result.all_passed 不为 False）、`success_rate = solved/total`、`avg_iterations`（iterations 列表长度的均值，缺省记 0）。解析失败的文件静默跳过。
- `classify(success_rate)`：`rate > easy_threshold`（默认 0.7）→ easy；`rate < hard_threshold`（默认 0.3）→ hard；其余 → medium。边界语义固定为"达到 easy 阈值即 easy、低于 hard 阈值即 hard"。
- `recalibrate(problems)`：有历史的题目按判定重标注；无历史的保留原难度并计入 `no_data`。

### CLI（src/main.py 新增 recalibrate 子命令）

- 参数：`--history`（必填，目录或文件）、`--output`（必填，重标注题库 JSON 输出路径）、`--dataset`（默认 `data/problems.json`）、`--easy-threshold`/`--hard-threshold`（默认 0.7/0.3，校验 `0 <= hard < easy <= 1`）、`--report`（可选，Markdown 报告路径，缺省打印 stdout）。
- 行为：加载题库（ProblemLoader）→ 聚合统计 → 重标注 → 写输出题库（Problem dump 列表，ensure_ascii=False）与报告；历史中无任何记录时报错退出码 1；阈值非法报错。
- 报告内容：重标注前后难度分布、逐题变更表（problem_id、原难度 → 新难度、成功率、平均迭代）、无历史数据题数。

## 边界

- 判定仅基于历史表现，不保证符合人类直觉难度；建议人工复核变更报告后使用输出题库。
- 输出文件不自动覆盖原 `--dataset`；由用户决定是否替换。
