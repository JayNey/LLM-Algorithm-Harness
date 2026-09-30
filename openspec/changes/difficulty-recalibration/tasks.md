# Tasks: difficulty-recalibration

## Task 1: 统计与判定模块

**文件**: 新增 `src/difficulty_calibration.py`、`tests/test_difficulty_calibration.py`

- [x] `collect_stats()`：历史 `*_results.json` 聚合（成功率、平均迭代、坏文件跳过）
- [x] `classify()`：阈值判定与边界语义；`recalibrate()`：无历史保留原标注并计 no_data
- [x] 单元测试：多记录聚合手算对账、三类边界、无历史、坏 JSON 跳过

## Task 2: CLI 子命令

**文件**: `src/main.py`、`tests/test_difficulty_calibration.py`

- [x] `harness recalibrate` 子命令与参数校验（阈值 0 <= hard < easy <= 1、缺 history 报错）
- [x] 输出题库 JSON 与 Markdown 报告（或 stdout）；无历史记录退出码 1
- [x] 端到端测试：tmp 目录构造历史与题库，断言输出内容与报告字段、退出码

## Task 3: 文档与回归

**文件**: `README.md`

- [x] 难度重标注使用说明（参数、判定口径、边界语义、人工复核建议）
- [x] 全量测试 + `openspec validate` 通过
