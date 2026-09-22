# Tasks: 模型对比分析面板

## Task 1: 结果矩阵与胜率统计

**文件**: `src/experiment_report.py`

- [x] 组装 模型×题 结果矩阵（重复按题取多数）；`budget_exhausted` 计为未解出
- [x] 同策略下模型两两配对，输出胜/平/负计数与比率，分母为题目总数
- [x] 单元测试：手算夹具（A 6 过 / B 4 过，交叉 3/1）胜平负与分母对账；budget_exhausted 配对场景

## Task 2: 显著性标注与成本效益

**文件**: `src/experiment_report.py`

- [x] McNemar 检验（math.comb 精确二项，零依赖）标注 p 值与显著性；不一致对不足时标"样本不足"
- [x] 成本效益：通过数/成本比排名；成本未知标注"未知"并排除排名
- [x] `comparison.json` 新增 `model_comparison` 段
- [x] 测试：显著/不显著/样本不足三分支；未知成本排除排名

## Task 3: 交互式 HTML 面板

**文件**: 新增 `src/experiment_panel.py`

- [x] `generate_html_panel(exp_dir)`：消费 comparison.json 渲染 `panel.html`
- [x] Chart.js（CDN）雷达图 / 散点图 / 柱状图，数据 JSON 内嵌；离线降级提示
- [x] 胜率矩阵 HTML 表格；成本未知模型不进散点图
- [x] runner 生成 comparison 后调用面板生成
- [x] 测试：panel.html 含三种图表数据与矩阵表格；成本未知排除断言

## Task 4: 组合粒度并行执行

**文件**: `src/models.py`, `src/experiment.py`

- [x] `ExperimentConfig.execution: serial|parallel`（默认 serial）与并行度配置
- [x] parallel：ThreadPoolExecutor 按组合并行，组合内逻辑与 serial 一致
- [x] 测试：serial 与 parallel 产出结构一致；并行度不超过上限

## Task 5: 文档与回归

**文件**: `docs/experiments.md`, `README.md`

- [ ] 文档补充：胜率/显著性/成本效益口径、panel.html 使用说明
- [ ] 全量测试 + OpenSpec validate 通过
