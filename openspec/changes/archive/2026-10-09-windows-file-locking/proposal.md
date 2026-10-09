# Proposal: windows-file-locking

对应上游 issue #138（Windows 兼容性 3/4：文件句柄与锁定修复）。

## Why

`src/incremental/history.py:5` 顶部 `import fcntl`（Unix 专属模块）导致 Windows 上 `ModuleNotFoundError`：5 个 incremental 测试模块在收集期即失败，Windows CI 从未真正跑过测试，也遮蔽了其他 Windows 缺陷的暴露（这是当前 Windows job 失败的首要死因）。同时临时文件用法审计发现 `src/benchmark/executor.py` 存在悬空句柄形态（NTF 不在 with 块内，异常路径泄漏句柄），属 issue 点名的审查范围。

## What Changes

- 新增 `src/utils/file_lock.py`：跨平台排他文件锁——Unix 用 `fcntl.flock`，Windows 用 `msvcrt.locking`（LK_NBLCK，锁首字节），两者皆缺的平台降级为 no-op（debug 日志声明）；不引入第三方依赖
- `src/incremental/history.py`：移除 `import fcntl`，`save()` 改用跨平台锁；"打开→加锁→写→解锁→关闭"次序与 3 次重试语义不变
- `src/benchmark/executor.py`：临时数据集从"悬空 NTF + 手动 close"改为 `mkstemp` + `os.fdopen` with 块形态（异常路径不泄漏句柄，与 `cost_alert._save_state` 既有模式一致）
- 新增守护与行为测试：锁语义（含平台分支模拟）、save 重试、fcntl 缺失时可导入、AST 扫描 src/ 全部 `NamedTemporaryFile`/`mkstemp` 处于 with 块内
- 范围排除：进程管理（#137）、路径分隔符/保留名（#139）、文本编码参数（#140 已覆盖）；已核实本 change 触达文件与 #140 零交集

## Capabilities

### New Capabilities

- `windows-compatibility`：Windows 兼容契约（文件锁定与句柄时序部分）。本 change 重建该 capability（前一版本随 PR #142 撤回未合入，编码类需求由 #140 的 `text-encoding` 承担）；后续 #137/#139 在同一 capability 下追加需求

### Modified Capabilities

（无）

## Impact

- 代码：`src/incremental/history.py`、`src/benchmark/executor.py`；新增 `src/utils/file_lock.py`
- 测试：新增锁与句柄守护测试；issue 指定验证文件 `tests/test_importers.py`、`tests/test_debug_e2e.py`
- 行为：Unix/macOS 上锁语义不变；Windows 上增量评估历史文件获得真实写锁，incremental 模块可导入
- 兼容性：不改公开 API；覆盖率门禁 `--cov-fail-under=90` 原样
