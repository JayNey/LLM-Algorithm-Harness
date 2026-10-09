# Design: windows-process-management

## Context

PR #143 Windows 运行（首次完整套件）的 30 个失败聚类：sandbox_executor 16 + sandbox_docker 4 为直接根因（`_run_command` 的 `selectors.DefaultSelector()` 在 Windows 对管道抛 WinError 10038；`_terminate_process_group` 在 Windows 只 kill 直接子进程，无进程组），experiment×6、error_analysis×1、integration×1、offline_e2e×2 为同因级联（全部经过 host 后端执行）。现有 Unix 路径行为：`start_new_session` + `os.killpg(SIGKILL)`；输出上限在泵取循环中即时触发终止；stdin 非阻塞写入。

## Goals / Non-Goals

Goals:

- host 后端在 Windows 上可执行、超时/限幅语义与 Unix 一致
- 进程树终止跨平台（超时、父退出两条路径，孙进程不残留）
- Unix 对外行为零变化（对外错误类型、CompletedProcess 形态、解码策略不变）

Non-Goals:

- 路径差异（#139）
- Docker 后端（其进程管理由容器隔离，未受影响）
- 输出解码策略（保持 `errors="replace"`，#140 领域）

## Decisions

1. **单一代码路径（线程泵）而非双路径**：stdout/stderr 各一个守护线程 `read(65536)` 入共享缓冲（锁内累计判限，超限置 event 并 `terminate_tree`），stdin 用独立守护线程喂入（BrokenPipeError 容忍，写毕关闭）；主线程轮询 `poll()` + deadline（20ms 粒度）。理由：Windows `select` 不支持管道是本 bug 根因，selectors 无 Windows 等价物；线程泵是 subprocess 官方推荐的可移植方案，且消除非阻塞 IO 的平台差异。风险（Unix 回归）由全量套件护航——原 selectors 语义（即时限幅、超时先于 wait、部分输出保留）在线程模型下逐条对应。
2. **Windows 进程树用 Job Objects**：`CreateJobObjectW` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` + `AssignProcessToJobObject(Popen._handle)`；终止走 `TerminateJobObject(job, 1)`，收尾 `CloseHandle`。KILL_ON_JOB_CLOSE 同时覆盖"父退出杀孙"契约（父死句柄关→树灭）。`AssignProcessToJobObject` 失败（嵌套 job/权限）降级为直接 kill + warning 日志，不阻断执行。
3. **`terminate_tree` 无条件且幂等**：sandbox `finally` 不再区分平台/进程存活（现状 `os.name != "nt" or poll() is None` 跳过 Windows 已死进程的清理正是孙进程残留的漏洞）。POSIX `killpg` 已容忍 `ProcessLookupError`；Windows `TerminateJobObject` 对已死树安全（FALSE + GetLastError 容忍），再兜底 `process.kill()`。
4. **分层**：`process_manager` 定义自有 `ProcessTimeoutError` / `OutputLimitExceededError`，不 import sandbox_executor；`_run_command` 薄封装映射为 `SandboxExecutionError("timeout"/"output_limit")`（外层现有匹配 "timeout" 的测试不受影响），`cleanup` 回调仍在 sandbox 层 finally 执行。
5. **跳过 selectors/`os.set_blocking`/`signal` 依赖**：`_run_command` 重写后这些导入若不再使用即移除（`_terminate_process_group` 保留为对 `terminate_tree` 的兼容包装直至确认无外部引用后随本 change 删除）。

## Risks / Trade-offs

- [线程泵与原 selectors 在极端时序下的输出完整性差异] → 退出后 join 线程排空管道再取返回码；限幅语义同样"超限即终止、保留已读部分"
- [Job Object 在 CI 运行器嵌套 job 场景的分配失败] → 降级直接 kill + warning；Windows 专属测试在 CI 实测（不 skip），失败即暴露
- [20ms 轮询粒度引入的超时误差] → 与原 selectors `select(remaining)` 的粒度量级一致（误差 ≤ 粒度），timeout_seconds 秒级配置下无感知
- [mypy/ctypes 平台分支] → Windows 专属 ctypes 结构体与调用集中在 `src/utils/process_manager.py` 的 `if os.name == "nt"` 分支，POSIX 导入不触碰；类型标注以 CI Type Check 为准

## Migration Plan

纯内部实现替换，无迁移。回滚 = revert 单个 PR。

## Open Questions

无。
