# 设计：规则推荐

推荐器扫描普通运行的 `*_results.json` 和实验组合结果，识别 `problem_id`、status、failure_category 和 hidden_result。题目元数据来自显式 `--dataset`，未提供时从 `metadata.json`/`experiment.json` 的 dataset_path 推断。

分组维度包括 difficulty、单个 tag、完整 tag 组合和 difficulty+tag 组合。每组记录失败数、总数、失败率和出现题目数；达到 `failure_threshold` 且满足 `min_samples` 才进入弱点报告。失败包括非 success 状态以及隐藏测试失败。

推荐只考虑历史中没有出现过的 problem_id。候选匹配一个或多个弱点分组，按最高失败率、失败次数和匹配分组数排序。输出报告 JSON，并在相同目录写出 `<output-stem>.problems.json`，其中只含标准 Problem JSON，可直接作为 `--dataset` 输入。
