# 验证报告：web-experiment-advanced-config

## 结论

6/6 任务完成；3/3 需求及 10/10 场景已有实现与有效证据，符合已批准 proposal、delta spec 与轻量设计。未发现 CRITICAL、IMPORTANT、WARNING 或规格偏差。沿用 tweak 的 direct/direct/off 配置，未进行独立 reviewer 审查。

## 完整性、正确性与一致性

| 维度 | 结果 |
| --- | --- |
| 完整性 | 同一 tasks.md 的 6 项全部完成；OpenSpec strict 校验通过 |
| 正确性 | 高级策略配置、筛选与回显、创建与组合预算 3 项需求均覆盖 |
| 一致性 | 白名单、空值省略、旧单预算兼容、原 ProblemLoader/ProblemBudget 语义均与设计一致；无后端端点或共享配置 schema 改动 |

## 场景映射

| 规格场景 | 实现与证据 |
| --- | --- |
| 非法草稿被本地拒绝 | validation.ts + validation.test.ts；无模型、非法预算拦截 |
| 创建后进入详情并可启动 | 原 session.tsx 导航与生命周期保持；client/runCreation 原回归通过；双语浏览器实际创建后导航到详情 |
| 整数预算无效时拦截创建 | validation.ts 的分维度错误；validation.test.ts 覆盖小数、零、负数及非法文本 |
| 发送选定预算 | BudgetFields / createExperimentPayload；完整三维 payload；Python stop 参数化测试分别确认 calls/tokens/seconds 的真实停止原因 |
| 不设置预算 | validation.test.ts 验证新预算均空为 null；旧草稿 budget_kind/budget_value 仍可转换 |
| 高级参数贯穿业务逻辑 | 新 Python 测试通过真实 HTTP 创建、SQLite 持久化、_build_runner_config、ExperimentRunner、self_consistency、LLMClient 到 mock SDK，核对候选数、max_tokens、temperature、system_prompt；客户端测试及浏览器核对回显 |
| 空配置与旧任务兼容 | frontend validation/client 回归及原 #492 继承回归；最终中英文浏览器用省略高级字段和筛选的旧响应验证默认配置与全部题目提示 |
| 高级输入错误可修正 | JSON 对象/键/类型/范围/枚举单元测试；浏览器 num_candidates=0 不提交、修正为 3 后提交成功，保留其余输入 |
| 组合筛选实际生效 | 浏览器核对 difficulty/tags/problem_ids/limit；Python 固定 6 题，执行及 ledger 仅包含 picked-a、picked-b，确认标签任一匹配、各条件交集及最后 limit |
| 未筛选与错误修正 | 空筛选省略、非法 limit 单元测试；浏览器旧任务显示未筛选的全部题目 |

## 实际检查

- `frontend/`: `npm test`：377 passed。最终仅补默认回显及双语资源，后续浏览器与资源覆盖检查已通过。
- 仓库根：`.venv/bin/python -m pytest -q --no-cov tests/test_web_experiment_config.py tests/test_strategy_parameter_contract.py tests/test_experiment.py`：103 passed。日志 `/tmp/issue526-python-regression.log`。
- `frontend/`: `npm run build`、`npm run lint`、修改的 14 个前端文件 `prettier --check`、最终 `src/i18n/resources.test.ts` 均通过。
- 仓库根：新 Python 测试 `ruff check`、`black --check` 及 `git diff --check` 均通过。
- 仓库根：`CHROME_PATH=<local Chrome> node frontend/scripts/verify-experiment-config.mjs`：中英文流程通过，无 pageerror。报告 `/tmp/issue526-browser/report.json`，表单、桌面与移动详情截图在同目录；人工查看表单与移动详情，配置和筛选可读。
- `comet classic openspec -- validate web-experiment-advanced-config --strict` 通过；Build Guard 接受真实检查报告并进入 Verify。
- 完整结构化结果见 `openspec/changes/web-experiment-advanced-config/checks.json`。

## 范围与边界

共 15 个交付文件（11 个实现/国际化、4 个测试），均对应 issue #526，未改变 scope、验收或风险类别，复用 `.comet/rulings.md` 中用户明确批准的文件数授权。

按 issue 使用本地 mock、小型题库；未启动真实 Eval、付费模型或沙箱部署。独立 reviewer 按 tweak 预设 review_mode=off 未执行。未运行全仓测试，不声明全仓覆盖率通过。首次 Python 调用因导入路径失败，改用 CI 的 python -m pytest；首次局部测试 4 项通过但被默认全仓 90% 覆盖率门槛判失败，随后按局部回归 `--no-cov` 得到 103 项通过。浏览器脚本早期 fixture 时间类型与 Ant Design 隐藏 option 选择问题均已定位修正，最终流程通过。

构建仅保留既有 CompareCharts 体积提示；没有新增依赖。已核对最终候选，无需为提交报告重复执行有效测试。

## PR 分支绑定复核

用户选择独立分支 PR 交付后，工作区从 main 重新绑定到 `codex/web-experiment-advanced-config`，基线 HEAD 仍为 `40a033e1ab4328697010f314ad5e12791e70dd4c`。实现、输入和执行环境未改变；已逐项核对既有检查仍覆盖当前候选，沿用实际有效结果。旧 main 归档提案失效，通过公开 reopen-verification 命令重开同一 Run 的 Verify；此次仅重新确认绑定与验收证据，不重演测试或实施。
