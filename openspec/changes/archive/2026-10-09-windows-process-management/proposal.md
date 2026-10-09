# Proposal: windows-process-management

对应上游 issue #137（Windows 兼容性 2/4：进程管理与沙箱跨平台抽象）。

## Why

`src/sandbox_executor.py` 的 host 后端 `_run_command` 用 `selectors.DefaultSelector()` 监听子进程管道——Windows 的 `select` 只支持 socket，管道注册即抛 `WinError 10038 (not a socket)`。PR #143（#138）解除收集期阻塞后，Windows 首次完整运行的 30 个失败中有 26 个直接源于此（sandbox_executor 16 + sandbox_docker 4 + experiment/integration/offline_e2e/error_analysis 级联 6+），另外 4 个进程组终止语义（超时/父退出后孙进程必须死亡）在 Windows 只有直接 kill，无进程组等价物。

## What Changes

- 新增 `src/utils/process_manager.py`：
  - `run_bounded()`：跨平台的有界子进程执行——stdout/stderr 用守护线程泵取（替代 select-on-pipes），合并字节数上限、stdin 喂入（独立线程、容断管）、deadline 超时；POSIX 与 Windows 单一代码路径
  - `spawn()` / `terminate_tree()`：POSIX `start_new_session` + `os.killpg`；Windows 用 ctypes Job Objects（`CreateJobObjectW` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` + `AssignProcessToJobObject`，超时/收尾 `TerminateJobObject` 杀整棵进程树；分配失败降级为直接 kill 并记日志）
- `src/sandbox_executor.py`：`_run_command` 切换到 `run_bounded`，`SandboxExecutionError("timeout"/"output_limit")` 语义保持；`finally` 无条件 `terminate_tree`（Windows 上 leader 已退出时孙进程也能被 job 清掉）
- 现有两个进程组终止测试（超时杀树 / 父退出杀树）转为全平台通过（Job Objects 使 Windows 满足同一契约），不添加 skipif
- 新增 tests/test_process_manager.py：超时、输出限幅、stdin 喂入、树终止幂等、Windows/POSIX 分支行为
- 范围排除：路径分隔符/保留名/大小写（#139）；编码参数（#140 已覆盖）

## Capabilities

### New Capabilities

（无——复用 #138 建立的 `windows-compatibility` capability）

### Modified Capabilities

- `windows-compatibility`：ADDED 进程树管理与跨平台有界执行需求（delta spec）

## Impact

- 代码：`src/sandbox_executor.py`（`_run_command` 重写为薄封装）；新增 `src/utils/process_manager.py`
- 测试：新增 tests/test_process_manager.py；既有 30 个 Windows 失败用例预期转绿（CI 验证）
- 行为：Unix 上对外语义不变（超时/限幅/输出字节流解码一致，实现从 selectors 换为线程泵）；Windows 上 host 后端首次可用
- 兼容性：不改公开 API；覆盖率门禁 `--cov-fail-under=90` 原样
