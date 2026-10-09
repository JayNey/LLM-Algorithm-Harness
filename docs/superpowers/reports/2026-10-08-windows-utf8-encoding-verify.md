# 验证报告：windows-utf8-encoding（上游 issue #136）

- 日期：2026-10-08
- 分支：comet/windows-utf8-encoding（基线 bd39236，本地快照对齐 upstream/main@3a21707）
- 验证模式：full（规模评估：9 任务 / 1 delta capability / 10 文件）；verify_mode=full（含 delta spec）
- 审查：两轮制。第一轮全量审查 approve（1 WARNING + 4 SUGGESTION）→ verify-fail 回 build 修复 → 第二轮定点复审（见 §审查结论）
- 注：tweak 预设 review_mode=off，按仓库交付惯例与"不得仅凭自评通过"协议补充独立审查者

## 检查结果简表（最终状态，第 2 轮 verify）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 9/9 `[x]`（tasks.md，authority revision 已核对） |
| 2 | 实现与 tasks 描述一致 | PASS | `git diff bd39236..HEAD` = 5 src 文件 14 处编码修复 + docker 探测异常补齐 + 守护测试 + openspec 产物，无超范围改动（两轮审查均核实） |
| 3 | 构建/测试通过（Runtime 证据） | PASS | 第 2 轮 build check exit=0（log e941f2b1）；verify check exit=0（log 73590169）：1106 passed / 4 skipped，coverage 90.72% |
| 4 | 相关测试通过 | PASS | tests/test_windows_utf8_io.py 4 条用例（主扫描 + 敏感性 + 阳性/阴性对照）通过 |
| 5 | 无安全问题 | PASS | 无密钥/注入引入；改动仅添加 encoding 参数、异常类型与测试 |
| 6 | 最终集成代码审查 | PASS | 第一轮 approve + 修复后定点复审 approve（见 §审查结论） |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate windows-utf8-encoding` → "Change 'windows-utf8-encoding' is valid"

## 场景核对（delta spec: windows-compatibility）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 文本文件读写显式 UTF-8 · cp1252 下读写非 ASCII | 静态保证：14 处全部显式 `encoding="utf-8"`（AST 守护测试锁定，平台无关语义）；Linux CI 无法真实模拟 cp1252 运行时，按 design 决策用静态守护替代 | PASS（静态） |
| 文本文件读写显式 UTF-8 · Unix 行为不变 | 全量测试在 macOS 通过（两轮 1104→1106 passed）；显式 encoding 与原 locale 默认相同；docker 探测异常面补齐后"探测失败→回退"契约恢复 | PASS |
| 子进程文本输出按 UTF-8 解码 · text=True 捕获 | 9 处 subprocess 均补 `encoding="utf-8"`；相关既有测试（mock subprocess）全量通过 | PASS |
| 文本 IO 编码守护 · 拦截回归 | 守护测试 4 用例（含别名形态与豁免矩阵对照）；人工变异验证（移除 experiment.py 一处 encoding → 红，恢复 → 绿）；第一轮审查中守护测试当场抓出第 14 处（sandbox_executor 脚本临时文件），真实回归下有效 | PASS |

## 审查结论

**第一轮（全量，`git diff bd39236..HEAD`）**：approve。0 CRITICAL / 0 IMPORTANT，1 WARNING + 4 SUGGESTION。核实要点：14 处编码点位置与参数正确；Unix 零回归；守护测试零误报（审查者独立复刻扫描证实）且在真实回归下抓出过第 14 处；`docker rm` 二进制捕获正确不在约束内；覆盖率门禁原样；无安全问题。

**WARNING 修复**：`_docker_available` 严格 UTF-8 解码可能击穿"探测失败→优雅回退"契约（Windows 上 docker CLI 输出非 UTF-8 时 UnicodeDecodeError 不在 except 内）→ 两处 except 追加 `UnicodeDecodeError` 返回 False（commit a8782f0），不掩盖输出、与"不加 errors="决策正交。

**SUGGESTION 修复**：守护测试补 subprocess 别名解析与 `.open()` 豁免清单/对照用例（commit 6f654e3）；proposal 计数 13→14 同步（commit ce39def）。

**第二轮（定点复审修复增量 a8782f0/6f654e3/ce39def）**：approve，未发现修复引入的新问题。逐条核对：WARNING 修法正确且复查全库无同类缺口（experiment/style/readability 为宽捕获已覆盖）；别名解析限定 `node.module == "subprocess"` 不误伤同名方法；22 条阳性/阴性对照逐例与规则实现一致。两条残留观察（当前 src/ 无触发、与 design 已声明方向一致）：`import os as o` 别名形态的低层 `o.open()` 会被误报；计算接收者的 `.open("w")`（如 `Path(x).open`）fail-open，spec 未要求该形态。

## 已知豁免（延续 design.md 决策，非本 change 缺陷）

- `src/incremental/history.py` `import fcntl`（Windows 收集期崩溃）：归 #138
- tests/ 既有约 80 处隐式编码写法：待 #138 解除收集期失败后按 Windows CI 实测定点修
- 守护测试对动态 `text=变量` 形态 fail-open：静态分析的已知边界，代码注释与 design 已声明
- 覆盖率门禁 `--cov-fail-under=90` 原样未动，实测 90.72%

## 结论

无 CRITICAL / WARNING 遗留问题（1 WARNING 已修复并经第二轮定点复审 approve 确认），两轮 verify 证据均 exit=0（1106 passed / 4 skipped，coverage 90.72%），验证通过，可进入归档确认。
