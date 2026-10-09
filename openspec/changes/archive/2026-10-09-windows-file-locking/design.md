# Design: windows-file-locking

## Context

语句级审计结论（2026-10-09，基线 fbae16f）：

- `import fcntl` 全仓仅 `src/incremental/history.py:5` 一处；`save()` 用 `flock(LOCK_EX)/LOCK_UN` 保护写，`load()` 无锁；测试零耦合
- 其余 9 处 tempfile 用法（task_service/cost_alert/cache/importers_base/sandbox_executor/code_quality×5）均为"with 块内写完→关闭→replace/unlink"时序，Windows 安全，无需改动
- 唯一结构缺陷：`src/benchmark/executor.py:94` NTF 悬空（手动 close，异常路径泄漏句柄）
- 与并行 PR #140 的文件交集为空（其触达 readability/style/experiment/main/sandbox_executor/logging），本 change 无冲突面

## Goals / Non-Goals

Goals:

- Windows 上 incremental 模块可导入、历史文件写有真实排他锁
- Unix 锁语义零变化
- 消除悬空句柄形态，并以守护测试锁定

Non-Goals:

- 进程组/Job Objects（#137）
- 路径分隔符/保留名/大小写（#139）
- 编码参数（#140）
- cache.py 固定名 `.tmp` 的并发碰撞（非 Windows 专属，遗留问题另立）

## Decisions

1. **锁原语链：`fcntl` → `msvcrt` → no-op 降级**。Unix `flock(LOCK_EX)`；Windows `msvcrt.locking(fd, LK_NBLCK, 1)` 锁首字节（Windows 允许锁 EOF 后区域，空文件可锁），非阻塞立即失败由调用方既有重试兜住；两者皆缺的平台 no-op + debug 日志（锁是并发优化，降级不应导致崩溃）。不引入 portalocker 等第三方依赖。**注意 `locking` 的区间相对当前文件位置**：加锁前记录锚点（`tell`），解锁前 `seek` 回锚——正文写入的缓冲刷盘会推进位置（≥8KB 负载必现），不回锚则解锁落在未加锁区域（独立审查 CRITICAL 发现，已修复并以 fake-msvcrt 偏移对称性测试锁定）。
2. **`history.save()` 次序与重试语义原样保留**（打开 w → 锁 → json.dump → 解锁 → 关闭，失败重试 3 次），只替换锁原语为 `exclusive_lock(f)` 上下文管理器。`load()` 维持无锁（现状即无锁，读侧风险不在本 issue）。
3. **`benchmark/executor.py` 改用 `mkstemp` + `os.fdopen(fd, "w", encoding="utf-8")`**：与 `cost_alert._save_state` 既有模式一致（issue 方案点名 mkstemp 优先）；写路径、`.name` 使用点、finally 清理逻辑保持不变。
4. **守护测试双层**：(a) AST 扫描 src/——每个 `NamedTemporaryFile(...)`/`mkstemp(` 调用必须处于 with 块内（Call 的语句级祖先含 With/AsyncWith），排除 `os.fdopen` 包装形态（fdopen 本身必须在 with 内）；(b) 行为测试——锁互斥与释放、fcntl 缺失时可导入（monkeypatch 模块属性模拟）、save 锁失败重试 3 次后抛 OSError。守护测试必须变异验证。
5. **不新增 `errors=`/`encoding=` 参数**：本 change 不碰编码（#140 并行处理），即使顺手也避免扩大冲突面。

## Risks / Trade-offs

- [msvcrt.locking 与 flock 语义差异（锁区间、继承、阻塞行为）] → 仅用非阻塞锁 + 既有重试，语义收窄为"立即成功或失败重试"，两侧一致；Windows 专属单测用 skipif 标注真实平台路径
- [no-op 降级平台失去并发保护] → 仅理论平台（同时缺 fcntl 与 msvcrt 的非 Windows 非 Unix）；debug 日志显式声明
- [#140 合入造成行号漂移] → 文件交集为空已核实；若合入顺序变化，交付前重放对齐（沿用 #142 撤回前验证过的重放流程）

## Migration Plan

纯内部实现替换，无迁移。回滚 = revert 单个 PR。

## Open Questions

无。
