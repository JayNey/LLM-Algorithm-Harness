## 1. 后端门禁

- [x] 1.1 在包含 #229/#230 的 main 基线上执行定向 Python、指定 API mypy、CI mypy、ruff、Black、编码检查与全量非 online pytest、src/api 覆盖率门禁；保存命令、SHA、退出码与警告/skip；失败调查后复验，禁止降低门槛。

## 2. 前端与验收矩阵

- [x] 2.1 执行 npm test/lint、tsc -b、build；逐项核对 #216–#230 和 issue #231 Step 1–5，更新 EVALUATIONS_CHECKS.md 与命令/日志证据；全部结论绑定实际执行提交和层级。

## 3. 审查与交付

- [x] 3.1 核对 diff、原始日志和全部验收条目，运行 git diff --check origin/main...HEAD 与 OpenSpec validate，记录审查结论、CI 证据或明确的未验证状态，再进入最终归档确认。
