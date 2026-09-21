# Tasks: 固定预算实验与可复现对比报告

## Task 1: 实验配置模型与加载

**文件**: `src/models.py`

- [x] 新增 `ExperimentConfig`（models × strategies × dataset_path × repeats × per-problem budget × output_dir）与校验
- [x] 新增 `experiment.example.json` 示例配置
- [x] 单元测试：配置解析、缺省值与非法值报错

## Task 2: 预算控制 BudgetTracker

**文件**: `src/budget.py`（预算原语独立模块，避免 runner ↔ harness 循环导入）, `src/harness.py`, `src/strategies/*.py`

- [x] 实现 `BudgetTracker`：每题调用数 / token（含推理 token）/ 耗时结算与 `allow_call()` 判断；`BudgetedLLMClient` 包装调用入口
- [x] Harness 模型调用前挂预算检查；耗尽时停止该题并记录停止原因与实际消耗（`budget_exhausted` 终态、不占用失败分类）
- [x] 无 usage 响应 + 硬 token 预算 → 组合标记 `token_budget_unsupported`
- [x] 单元测试：三类预算各自触发停止；无 usage 标注

## Task 3: 实验编排与可复现元数据

**文件**: `src/experiment.py`

- [ ] 遍历 (模型, 策略, 重复) 组合，复用 AlgorithmHarness 执行并落盘 `results/experiments/<id>/`
- [ ] 写实验级 `experiment.json`：题集 SHA-256 + 题目 ID 列表、git commit、有效模型参数、预算、定价快照（source + as_of）
- [ ] 预算耗尽题目进未完成清单；统计总数 / 完成 / 未完成
- [ ] 测试：离线假模型客户端下端到端跑通 2 策略 × 2 重复，目录与元数据断言

## Task 4: 未知定价显式标记

**文件**: 成本估算模块、`pricing_metadata` 写入、报告成本展示

- [ ] 无可用定价 → 未知标记 + 空成本 + 警告（含模型名），删除默认单价折算
- [ ] `pricing_metadata` 保留未知标记；HTML / Markdown 报告显示"未知"，不显示 $0
- [ ] 测试：未知模型不再产生默认价金额；已知模型定价行为不变

## Task 5: 对比报告生成

**文件**: `src/experiment_report.py`

- [ ] 聚合各组合结果：隐藏通过率、样例验证率、失败类型分布（含 budget_exhausted）、修复率、平均调用数 / token / 耗时；按难度与标签分组
- [ ] 重复 ≥ 2 时输出跨重复最小 / 最大范围与不确定性说明
- [ ] 输出 `comparison.json` / `comparison.csv` / `REPORT.md`；成本未知显示"未知"
- [ ] 测试：固定夹具（正确解 / 样例过拟合 / API 失败 / 预算耗尽）手算对账，分母 = 成功 + 各失败 + 未完成

## Task 6: CLI 子命令与文档

**文件**: `src/main.py`, `README.md` 或 `docs/`

- [ ] 新增 `harness experiment --config <file> [--output-dir <dir>]` 子命令与退出码
- [ ] 文档补充实验配置字段、报告口径与示例
- [ ] 全量测试 + 离线回归套件通过
