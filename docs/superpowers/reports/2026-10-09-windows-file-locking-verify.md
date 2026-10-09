# 验证报告：windows-file-locking（上游 issue #138）

- 日期：2026-10-09
- 分支：comet/windows-file-locking（基线 1621fb9，本地快照对齐 upstream/main@fbae16f）
- 验证模式：full（8 变更文件 / 1 delta capability / 7 任务）；verify_mode=full（含 delta spec）
- 审查：两轮制。第一轮全量审查 requests-changes（1 CRITICAL + 1 IMPORTANT + 2 WARNING + 2 SUGGESTION）→ verify-fail 回 build 全部修复 → 第二轮定点复审 approve（见 §审查结论）
- 注：tweak 预设 review_mode=off，按仓库交付惯例与"不得仅凭自评通过"协议补充独立审查者

## 检查结果简表（最终状态，第 2 轮 verify）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 7/7 `[x]` |
| 2 | 实现与 tasks 描述一致 | PASS | `git diff 1621fb9..HEAD` 共 7 提交 10 文件（file_lock/history/executor + 守护测试 + 变异证据 + 产物），两轮审查均核实范围无超界 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | 第 2 轮 build check exit=0（log cd2ecf7f）；verify check exit=0（log 8d3360fa）：1125 passed / 4 skipped，coverage 90.63%（file_lock.py 100%） |
| 4 | 相关测试通过 | PASS | tests/test_windows_file_handles.py 10 条（含 fake-msvcrt 偏移对称回归）全过；issue 指定 tests/test_importers.py、tests/test_debug_e2e.py 及增量相关 8 文件 70 passed |
| 5 | 无安全问题 | PASS | 无密钥/注入引入；锁原语与句柄时序改动经两轮审查 |
| 6 | 最终集成代码审查 | PASS | 第一轮 requests-changes → 修复后第二轮定点复审 approve（见 §审查结论） |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate windows-file-locking` → valid

## 场景核对（delta spec: windows-compatibility）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 跨平台历史文件写锁 · Unix 行为不变 | save() 次序与重试语义经与基线逐行比对等价（首轮审查核实）；全量测试 macOS 通过 | PASS |
| 跨平台历史文件写锁 · 无 fcntl 平台可导入可保存 | AST 守护断言 src/ 无直接 fcntl 导入/ImportFrom（file_lock.py 豁免）；monkeypatch 双缺平台 save/load 正常；**Windows msvcrt 路径经 fake-msvcrt 偏移对称性测试锁定**（首轮审查 CRITICAL 的回归测试，M1 变异互证） | PASS |
| 跨平台历史文件写锁 · 锁失败按重试语义放弃 | monkeypatch 锁抛 OSError → 恰好重试 3 次后抛 OSError | PASS |
| 临时文件句柄先关后删 · 守护拦截悬空句柄 | AST 扫描（NTF/fdopen 须在 with 块、mkstemp 须 (fd,name) 元组且 fd 经 fdopen-with 消费、直接名导入识别）+ 阳/阴性对照 6+5 条；M2 变异红→绿 | PASS |
| 临时文件句柄先关后删 · benchmark 异常路径不泄漏 | 行为测试：harness 抛错后 mkstemp 临时文件被清理；dump 失败路径经 try/except 清理（复审确认，专属用例列为后续改进） | PASS |

## 审查结论

**第一轮（全量，`git diff 1621fb9..4c045e7`）**：requests-changes。1 CRITICAL + 1 IMPORTANT + 2 WARNING + 2 SUGGESTION：
- **CRITICAL（msvcrt 解锁位置漂移）**：`msvcrt.locking` 区间相对当前文件位置，缓冲刷盘（≥8KB 负载）推进位置后解锁落在未加锁区域 → save 必然失败。**修复**：锁前 `flush()+tell()` 记锚，解锁前 `seek(anchor)` 回锚（seek 先刷缓冲），commit aa1fb7a；新增 fake-msvcrt 偏移对称性测试（20000 字节写入体），M1 变异精确红在 `[(1,0,1),(2,20000,1)]` 与机制吻合
- **IMPORTANT（msvcrt 分支零覆盖）**：由上述对称性测试消除
- **WARNING×2（守护绕过形态 / fcntl ImportFrom 盲区）**：扫描器升级（直接名导入、裸/单名 mkstemp、fdopen 关键字、fcntl ImportFrom）+ 对照扩充，commit 7afcc0a
- **SUGGESTION×2（dump 失败残留 / 变异证据未持久化）**：executor dump 路径纳入清理；变异证据落盘 docs/superpowers/reports/2026-10-09-windows-file-locking-mutations.md

**第二轮（定点复审 aa1fb7a + 7afcc0a）**：approve。六项逐条确认修复正确、无新阻塞问题。三条非阻塞残留（不计入本次范围）：executor dump 失败分支无专属行为测试（全量覆盖间接覆盖）；`from os import fdopen` 直接名形态为 fail-closed 方向盲区（无现行违规）；历史记录仍是首轮数字的报告文件已由本轮刷新。

## 变异验证附录

见 docs/superpowers/reports/2026-10-09-windows-file-locking-mutations.md（M1/M2/M3 各含变异红与恢复绿；M3 首次变异无效——插入点落在 docstring——已如实注记并重做）。

## 已知豁免（延续 design.md 决策，非本 change 缺陷）

- 进程管理（#137）、路径差异（#139）：明确排除
- 编码参数：#140 并行处理（文件交集已核实为空）
- cache.py 固定名 `.tmp` 并发碰撞：design.md Non-Goals
- no-op 降级平台失去并发保护：design.md 已声明取舍
- 覆盖率门禁 `--cov-fail-under=90` 原样未动，实测 90.63%

## 结论

无遗留 CRITICAL/IMPORTANT/WARNING（首轮 6 项全部修复并经第二轮定点复审 approve），第 2 轮 build/verify 证据均 exit=0（1125 passed / 4 skipped，coverage 90.63%），验证通过，可进入归档确认。
