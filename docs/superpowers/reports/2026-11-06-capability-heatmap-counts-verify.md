# #365 验证报告

## 当前结论

实现、回归和最终独立集成审查通过。阶段 Guard 收尾中；本报告不替代远端 CI。

## 范围与根因

难度与标签统一按模型汇总所有策略/repeat 的真实 solved/total；重算 rate，稳定排序；零分母为 null，未知或无效计数保守地使整格未知。实验报告分组→panel→嵌入 HTML JSON 可逐项对账。

基线：main `c9ae42076a2b54f57302ee0a63555acb1ed627c6`，开工时远端 10 项检查均 success。无未合并前置依赖，独立分支和 PR。

## 实际验证

- 原实现的仓库内失败回归：12 failed / 2 passed（日志 `/tmp/365-red-repo.log`）。失败对应目标行为；早期临时脚本的参数/替身错误未计作 RED。
- 修复后的定向验证：14 passed（`/tmp/365-green.log`）。
- 相关模块回归：208 passed（`/tmp/365-regression.log`）。
- 全仓库 Ruff、Black、src 101 个源文件 mypy、显式编码（0 个问题）和 diff 空白检查通过。
- OpenSpec strict 校验通过；Runtime 本地 compileall 构建成功（`/tmp/365-build-check.log`）。

## 可重复检查命令

```bash
python -m pytest tests/test_capability.py tests/test_experiment.py tests/test_capability_profiler.py tests/test_capability_radar_integration.py tests/test_pareto.py tests/reporting -q --no-cov
python -m ruff check .
python -m black --check .
python -m mypy src/ --ignore-missing-imports
python scripts/find_missing_encoding.py
```

## 独立集成审查

独立 reviewer `/root/review_365_final` 审查最终产品 diff、规格与测试，通过，无 actionable 问题。独立运行 capability + experiment 测试 58 passed；额外验证 1/1 + 0/9 正序/反序均为 1/10。

## 验证边界

未新增浏览器截图；图表布局和 JS 未变，验证使用真实 panel 数据与 HTML 序列化，无付费模型调用。

两项改动各自仅涉及一个业务模块，不新增 API、数据库 schema、依赖或并发模型。虽包含测试与文档多个文件，仍按已授权自主选择的局部 hotfix 处理；没有更改现有接口契约。
