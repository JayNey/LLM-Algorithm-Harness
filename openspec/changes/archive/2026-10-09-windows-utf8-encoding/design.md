# Design: windows-utf8-encoding

## Context

上游 CI（PR #117 引入）Windows job 恒红。当前最新失败点是 `src/incremental/history.py:5` 的 `import fcntl` 在 Windows 无此模块，导致 5 个 incremental 测试文件收集期即失败（归 #138）；编码类失败被遮蔽。对 src/ 的语句级扫描显示存量缺 encoding 的文本 IO 共 13 处，集中在 code_quality 分析器、experiment 的 git 调用、sandbox_executor 的 docker 调用与 main.py 的一处 read_text。报告生成、导入器、推荐引擎等 issue 点名模块在近期 PR 中已补齐 encoding。

## Goals / Non-Goals

Goals:

- src/ 全部文本模式文件 IO 与 `text=True` 子进程调用显式 `encoding="utf-8"`
- 用守护测试锁定契约，防止回归
- Unix 行为零变化

Non-Goals:

- 不修 `fcntl`/进程组（#137、#138）
- 不修路径分隔符/保留名/大小写（#139）
- 不批量改 tests/ 固件编码（#138 后按 Windows CI 实测定点处理）
- 不引入 `PYTHONUTF8=1`、PEP 686 `utf-8 mode` 等运行环境要求

## Decisions

1. **逐点显式 `encoding="utf-8"`，而非全局 utf-8 mode**：不要求用户改环境变量或解释器选项，对第三方库调用无全局副作用；与 issue 方案同口径。备选的 `PYTHONUTF8=1`（CI 注入）只能救 CI 不能救用户，PEP 686 尚未到各支持版本稳定期。
2. **subprocess 用 `text=True, encoding="utf-8"`，不加 `errors=`**：保持严格解码，让真实乱码暴露而非被替换掩盖。git/docker 的文本输出按文档为 UTF-8；若未来出现真实非 UTF-8 输出，再在后续 change 单独评估 errors 策略。
3. **`NamedTemporaryFile` 只补 encoding，不动 `delete=False` 与句柄生命周期**：句柄释放是 #138 的核心，避免两个 PR 改同一批行冲突。
4. **守护测试用 AST 扫描而非运行时模拟 Windows locale**：Linux CI 无法真实模拟 cp1252 运行时；AST 规则（`ast.parse` + `ast.walk` Call 节点检查关键字）比正则稳，能正确处理多行调用。规则：src/**/*.py 中文本模式 `open()`、`Path.read_text()`/`write_text()`、`mode="w"` 的 `NamedTemporaryFile`、文本模式 `fdopen`、`text=True` 的 subprocess 必须出现 `encoding=`；bytes 模式与 `os.open` 等低层 fd 调用豁免。subprocess 规则解析 `import subprocess as x` 与 `from subprocess import run` 两种别名形态；`.open()` 规则仅匹配简单 Name 接收者并维护非文本模块豁免清单（webbrowser/tarfile/zipfile 等）。豁免矩阵与别名形态由阴性/阳性对照用例固定。守护测试必须做变异验证（临时移除一处 encoding 确认变红）。
5. **tests/ 存量不动**：80 处多为 ASCII 固件，实际会在 Windows 触发的子集未知；等 #138 解除收集期失败后按 CI 日志定点修，避免本 PR 膨胀到 22 个测试文件稀释审查。

## Risks / Trade-offs

- [pylint/black/radon 等工具输出含非 UTF-8 字节时严格解码抛错] → 这些为可选依赖，当前测试均 mock subprocess，生产路径默认不启用；出现时属真实环境问题，应显式处理而非掩盖
- [守护测试规则过严误伤合法写法] → 仅约束文本模式；bytes/低层 fd 豁免有测试固定
- [覆盖率门禁 90% 不可动摇] → 新增测试只增不减；完成后全量跑 `pytest -m "not online"` 核对

## Migration Plan

纯加参数改动，无迁移。回滚 = revert 单个 PR。

## Open Questions

无。
