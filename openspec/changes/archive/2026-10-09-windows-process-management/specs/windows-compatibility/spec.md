# windows-compatibility Specification

## Delta

`## ADDED Requirements`（归属 capability：windows-compatibility，由 windows-process-management 追加）

## ADDED Requirements

### Requirement: 跨平台进程树终止

沙箱子进程 SHALL 以可整树终止的方式启动：POSIX 使用新会话（`start_new_session`）并以 `killpg` 终止；Windows 使用 Job Object（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）并以 `TerminateJobObject` 终止。超时与正常收尾路径 SHALL 都执行树终止且幂等；Windows 上 leader 进程已退出时 SHALL 仍能终止树内残留子进程。Job Object 分配失败时 SHALL 降级为直接 kill 并记录 warning。

#### Scenario: 超时后孙进程不残留

- **WHEN** 子进程又派生孙进程、命令超时被终止
- **THEN** 孙进程随树一同死亡（对孙进程 pid 发信号返回进程不存在），POSIX 与 Windows 行为一致

#### Scenario: leader 提前退出后孙进程不残留

- **WHEN** 子进程派生孙进程后自行退出（sys.exit(0)）
- **THEN** 执行收尾仍终止整树，孙进程不残留

### Requirement: 跨平台有界子进程执行

有界执行 SHALL 在所有平台支持：stdout/stderr 并发泵取（不依赖 POSIX 专属的管道 select）、合并输出字节数上限（超限立即终止并报 `output_limit` 语义）、stdin 数据喂入（对端关闭时容忍断管）、deadline 超时（报 `timeout` 语义）。超时与超限路径 SHALL 保留已读取的输出。

#### Scenario: host 后端在 Windows 可执行

- **WHEN** 在 Windows 上经 host 后端执行任意题目代码（含 stdin_stdout 与 function 两种模式）
- **THEN** 执行正常完成，不抛 WinError 10038/not a socket

#### Scenario: 输出超限立即终止

- **WHEN** 子进程输出超过配置的字节数上限
- **THEN** 执行立即终止并返回 output_limit 语义错误，已读输出保留，进程树不残留

#### Scenario: Unix 对外语义不变

- **WHEN** 在 macOS/Linux 上运行既有沙箱与全量测试
- **THEN** 超时/限幅/输出内容与改动前一致
