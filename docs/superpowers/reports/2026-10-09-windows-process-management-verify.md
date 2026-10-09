# 验证报告：windows-process-management（上游 issue #137）

- 日期：2026-10-09
- 分支：comet/windows-process-management（基线 64ea615，本地快照对齐 upstream/main@4da05964，已含 #138）
- 验证模式：full（8 变更文件 / 1 delta capability / 8 任务）；verify_mode=full（含 delta spec）
- 审查：两轮制。第一轮全量审查 requests-changes（3 IMPORTANT + 4 WARNING + 4 SUGGESTION）→ verify-fail 回 build 全部修复 → 第二轮定点复审 approve（见 §审查结论）
- 注：tweak 预设 review_mode=off，按仓库交付惯例与"不得仅凭自评通过"协议补充独立审查者

## 检查结果简表（最终状态，第 2 轮 verify）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 8/8 `[x]` |
| 2 | 实现与 tasks 描述一致 | PASS | `git diff 64ea615..HEAD` 共 6 提交 10 文件（process_manager + sandbox 切换 + 测试 + 变异证据 + 产物），两轮审查均核实范围无超界 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | 第 2 轮 build check exit=0（log 3a5b6d38）；verify check exit=0（log a8d111e7）：1151 passed / 4 skipped，coverage 90.43% |
| 4 | 相关测试通过 | PASS | tests/test_process_manager.py 8 条全过（跨平台无 skipif）；sandbox 两文件 46 passed；2.3 级联文件 71 passed |
| 5 | 无安全问题 | PASS | 无密钥/注入引入；ctypes 仅固定 kernel32 API 并声明 restype/argtypes |
| 6 | 最终集成代码审查 | PASS | 第一轮 requests-changes → 修复后第二轮定点复审 approve（见 §审查结论） |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate windows-process-management` → valid

## 场景核对（delta spec: windows-compatibility）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 跨平台进程树终止 · 超时后孙进程不残留 | test_terminate_tree_kills_grandchild + docker 超时杀树测试（M1 变异红→绿）；Windows 路径由 Job Object 于 CI 实测 | PASS |
| 跨平台进程树终止 · leader 提前退出后孙进程不残留 | 完成条件 = 进程退出 AND 泵 EOF（M2 变异红→绿）+ docker 父退出测试；存活探针经 I-3 修复为跨平台 `_pid_alive`（OpenProcess + STILL_ACTIVE） | PASS |
| 跨平台有界执行 · host 后端 Windows 可执行 | selectors-on-pipes 根因移除；mypy 增量归零（I-1 修复经审查者独立复刻环境实测：10 既有/0 增量）；Windows 实测待 PR CI | PASS（静态+POSIX 实测） |
| 跨平台有界执行 · 输出超限立即终止 | test_run_bounded_output_limit_raises_and_preserves_output 断言异常携带部分输出（W-4 修复后） | PASS |
| 跨平台有界执行 · Unix 对外语义不变 | 错误类型/CompletedProcess 形态/解码策略不变；全量 1151 passed（macOS） | PASS |

## 审查结论

**第一轮（全量，`git diff 64ea615..1c6e0a2`）**：requests-changes。3 IMPORTANT + 4 WARNING + 4 SUGGESTION：
- **I-1（mypy 8 错，CI Type Check 将红）**：`_sandbox_job` 属性 / 未标注 stream / 4 个无效 ignore → setattr/getattr 化、`IO[bytes]` 标注、删除无效 ignore
- **I-2（normal_path Windows CRLF 必炸）** → 断言前归一化
- **I-3（`os.kill(pid,0)` 探针 POSIX 专属且在 Windows 误杀活进程）** → 两处 docker 测试探针替换为跨平台 `_pid_alive`
- **W-1（变异证据夹带无效运行）/ W-2（job 句柄泄漏）/ W-3（terminate_tree 并发句柄竞态）/ W-4（spec"保留已读输出"无实现载体）** → 证据重写、失败分支 CloseHandle、`_job_lock` 先清后用、异常携带 stdout/stderr
- **S-1~S-4**：start 入 try、ctypes restype/argtypes、docstring、design 笔误——全部落地

**第二轮（定点复审 43add51）**：approve。11 条逐条确认修复有效且无新缺陷；审查者独立实测：mypy（复刻环境冷缓存）10 既有/增量 0、全量 1151 passed / coverage 90.43%、black/ruff 绿。非阻塞残留一条（R-1：finally join 对未 start 线程会掩盖 start 异常的语义问题，列为后续顺手项）。

## 变异验证附录

docs/superpowers/reports/2026-10-09-windows-process-management-mutations.md（W-1 修复后版本）：
- M1 run_bounded finally 移除 terminate_tree → 超时杀树测试红 → 恢复绿
- M2 完成条件退化为仅 poll() → 父退出杀树测试红 → 恢复绿

## 已知豁免（延续 design.md 决策，非本 change 缺陷）

- 路径差异（#139）、编码（#140 已覆盖）、Docker 后端：明确排除
- stdin 喂入语义差异（阻塞线程 vs 非阻塞立即关闭）：design.md 决策 1 已声明
- Job Object 分配失败降级直接 kill：design.md 决策 2 已声明（失败分支句柄泄漏已在 W-2 修复中消除）
- 覆盖率门禁 `--cov-fail-under=90` 原样未动，实测 90.43%

## 结论

无遗留 CRITICAL/IMPORTANT/WARNING（首轮 11 项全部修复并经第二轮定点复审 approve），第 2 轮 build/verify 证据均 exit=0（1151 passed / 4 skipped，coverage 90.43%），验证通过，可进入归档确认。
