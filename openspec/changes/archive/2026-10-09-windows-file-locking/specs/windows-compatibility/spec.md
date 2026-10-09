# windows-compatibility Specification

## Purpose

建立 Windows 兼容契约中"文件锁定与句柄时序"部分：历史运行记录的并发写保护在所有平台真实生效（或显式降级），临时文件句柄遵循"先关后删"时序。本 capability 由上游 issue #138 重建（编码类需求由 `text-encoding` capability 承担）；后续 #137（进程管理）、#139（路径差异）在同一 capability 下追加需求。

## ADDED Requirements

### Requirement: 跨平台历史文件写锁

`IncrementalHistory.save()` 的并发写保护 SHALL 在 fcntl（Unix）、msvcrt（Windows）之上实现为跨平台排他锁，且 SHALL NOT 因平台缺少 fcntl 而无法导入或保存；两者皆缺时锁 SHALL 降级为 no-op 并输出 debug 日志。锁获取失败时 SHALL 保留既有的重试语义（默认 3 次后抛 OSError）。

#### Scenario: Unix 锁行为不变

- **WHEN** 在 macOS/Linux 上并发调用 save() 与既有测试
- **THEN** 写入串行化、内容完整，行为与改动前一致

#### Scenario: 无 fcntl 平台可导入可保存

- **WHEN** 在没有 fcntl 模块的平台上导入 `src.incremental.history` 并执行 save()
- **THEN** 模块导入成功、保存成功（Windows 经 msvcrt 真实加锁），不抛 ModuleNotFoundError

#### Scenario: 锁获取失败按重试语义放弃

- **WHEN** 锁持续被占用导致加锁失败
- **THEN** save() 重试至默认 3 次后抛出 OSError，且日志记录每次失败

### Requirement: 临时文件句柄先关后删

src/ 中所有 `tempfile.NamedTemporaryFile` 与 `tempfile.mkstemp` 的使用 SHALL 处于 with 块（或 `os.fdopen` 包装的 with 块）内，保证任何路径上的删除/替换发生在句柄关闭之后。

#### Scenario: 守护扫描拦截悬空句柄

- **WHEN** src/ 下出现不在 with 块内的 NamedTemporaryFile/mkstemp 调用
- **THEN** 守护测试失败并列出违规位置

#### Scenario: benchmark 执行异常路径不泄漏句柄

- **WHEN** benchmark 套件执行中途抛出异常
- **THEN** 临时数据集文件仍被清理，且清理发生在句柄关闭之后（无悬空句柄形态）
