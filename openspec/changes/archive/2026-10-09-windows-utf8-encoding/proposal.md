# Proposal: windows-utf8-encoding

对应上游 issue #136（Windows 兼容性 1/4：UTF-8 编码修复）。

## Why

Windows 默认文本编码是 cp1252/charmap（非 UTF-8），产品代码中仍存在未显式指定 `encoding` 的文本文件读写与子进程文本解码。读写含非 ASCII 内容（中文题面、报告、Markdown）时抛 `UnicodeEncodeError`/`UnicodeDecodeError`。上游 CI 的 Windows job 当前恒红；更早的失败还被 incremental 模块 `import fcntl` 的收集期崩溃遮蔽（该问题归 #138，本 change 不处理）。

## What Changes

- 为 src/ 下全部无显式编码的文本 IO 补 `encoding="utf-8"`，共 5 文件 14 处：
  - `src/code_quality/readability_analyzer.py`：3 处文本模式 `NamedTemporaryFile` + 3 处 `subprocess(..., text=True)`（pylint/flake8/radon）
  - `src/code_quality/style_analyzer.py`：1 处 `NamedTemporaryFile` + 1 处 subprocess（black）
  - `src/experiment.py`：2 处 git subprocess
  - `src/sandbox_executor.py`：2 处 docker subprocess + 1 处脚本写入 `NamedTemporaryFile`（第 14 处由守护测试当场抓出补修）；docker 探测的异常处理补 `UnicodeDecodeError` 保持"探测失败→回退"契约
  - `src/main.py`：1 处 `read_text()`（运行状态读取）
- 新增 AST 守护测试 `tests/test_windows_utf8_io.py`：静态扫描 src/，禁止新增无显式 encoding 的文本 IO（含 subprocess 别名导入解析、非文本 `.open()` 豁免清单与阴性/阳性对照用例）。
- 范围排除：`fcntl` 文件锁定与临时文件句柄释放（#138）、进程组/Job Objects（#137）、路径分隔符与 Windows 保留名（#139）。tests/ 下现存约 80 处无 encoding 写法本 change 不动（多为 ASCII 固件，待 #138 修复收集期失败后由 Windows CI 实测暴露真实缺口再定点补）。

## Capabilities

### New Capabilities

- `windows-compatibility`：跨平台文本 IO 编码契约。本 change 建立该 capability，后续 Windows 兼容子 issue 在同一 capability 下追加需求。

### Modified Capabilities

（无）

## Impact

- 代码：`src/code_quality/readability_analyzer.py`、`src/code_quality/style_analyzer.py`、`src/experiment.py`、`src/sandbox_executor.py`、`src/main.py`；新增 `tests/test_windows_utf8_io.py`
- 行为：Unix/macOS 上无行为变化（显式 encoding 与 locale 默认相同）；Windows 上文本 IO 固定按 UTF-8
- 兼容性：不改公开 API、CLI 参数与输出格式；覆盖率门禁 `--cov-fail-under=90` 保持原样
