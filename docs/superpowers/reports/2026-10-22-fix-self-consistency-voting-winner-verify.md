# Self-Consistency 投票胜者代码修复验证

## 结论

PASS。`generated_code` 现在来自投票选中的候选，与最终沙箱结果一致。修复提交：`86e01c9`。工作分支：`hotfix/20261022/fix-self-consistency-voting-winner`。

## 根因与改动

原投票函数只传出胜者沙箱结果，通用结果构造器却读取最后一次迭代代码。现在投票函数同步返回 `selected_code`，Self-Consistency 在构造结果后采用该值；不改变公共接口或其他策略。全失败仍采用最后候选回退，平票仍采用首次出现的代码，完整候选顺序和 token/traces 保留。

## 轻量验证六项

1. PASS：tasks.md 三项均已完成。
2. PASS：实际功能改动仅涉及 Self-Consistency 实现及一个相关测试文件，与任务一致。
3. PASS：Python wheel 构建成功。
4. PASS：Self-Consistency 相关测试 18 项通过；策略/Harness 相关测试 79 项通过；全量离线测试 2875 项通过、7 项跳过，覆盖率 91.70% ≥ 90%。
5. PASS：diff 未引入凭证、不安全执行或新增外部操作，`git diff --check` 通过。
6. PASS：hotfix 默认 `review_mode: off`，按流程跳过自动集成代码审查；已核对最终 diff 与回归证据。

自动规模评估统计 14 个文件（包含 Comet 状态、快照及说明文件），因此判为 full。实际实现及测试共 2 个文件、3 个任务、0 个 delta spec；按技能允许手动设置为 light。无新增 capability、公共接口、schema 或跨模块协调改动。

## 可复现证据

- RED：`python3 -m pytest tests/strategies/test_self_consistency_e2e_report.py -k generated_code_matches_selected_candidate --no-cov -q` 在修复前为 6 failed、4 passed。多数候选为 `print(5)` 时错误返回末尾的 `print(2 + 3)`；末尾失败/无代码/模型异常、平票、中间唯一通过也均返回错误代码。
- GREEN：`python3 -m pytest tests/strategies/test_self_consistency_e2e_report.py tests/strategies/test_self_consistency_report.py --no-cov -q`：18 passed。
- 扩大验证并在 verify 阶段独立重跑：`python3 -m pytest tests/strategies tests/test_strategies.py tests/test_harness.py --no-cov -q`：79 passed。
- 全量：`python3 -m pytest -m 'not online'`：退出码 0；2875 passed、7 skipped、121 warnings；323.26 秒。覆盖率门槛通过。日志：`/private/tmp/self-consistency-voting-winner-pytest.log`。
- 10 个参数化场景验证返回代码、选中测试结果、候选顺序、token 汇总、trace 数量、投票频次及序列化。另通过只读 Python 断言验证空候选返回空代码、无沙箱结果、success=False。
- `ruff check src/strategies/self_consistency.py tests/strategies/test_self_consistency_e2e_report.py`：通过。
- `black --check src/strategies/self_consistency.py tests/strategies/test_self_consistency_e2e_report.py`：通过。
- `python3 -m mypy src/strategies/self_consistency.py --ignore-missing-imports`：通过。
- `python3 scripts/find_missing_encoding.py`：0 项。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /private/tmp/self-consistency-voting-winner-dist`：成功生成 `llm_algorithm_harness-0.1.0-py3-none-any.whl`。
- `comet classic openspec -- validate fix-self-consistency-voting-winner`：有效；恢复既有功能、不改变 spec 验收要求，使用 `skip_specs: true`。

## 限制与状态

全量运行有 121 条警告，涉及模型类测试收集、依赖弃用及数值/绘图提示，没有测试失败。在线供应商和被跳过的环境相关场景未验证。

未提交改动均为本 change 的验证报告及 Comet 阶段状态，不包含用户原有改动。`branch_status` 保持 pending；归档与远端交付等待用户最终确认。Comet 可选个人记忆插件因全局状态锁写权限失败，未影响修复、测试或阶段守卫。

## 归档交付确认

验证完成后用户明确选择「归档、提交、推送并创建 PR」。本次交付包含实现提交与唯一归档提交，目标分支为 `main`，不执行合并。
