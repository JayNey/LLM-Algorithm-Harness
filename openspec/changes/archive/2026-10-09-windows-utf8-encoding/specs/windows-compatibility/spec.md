# windows-compatibility Specification

## Purpose

建立跨平台文本 IO 的编码契约：产品代码的文本文件读写与子进程文本解码显式使用 UTF-8，使 Windows（cp1252 等非 UTF-8 默认 locale）与 Unix 行为一致。本 capability 由上游 issue #136 建立；后续 Windows 兼容子 issue（进程管理 #137、文件锁定 #138、路径差异 #139）在同一 capability 下追加需求。

## ADDED Requirements

### Requirement: 文本文件读写显式 UTF-8

产品代码（src/）中的文本模式文件读写 SHALL 显式指定 `encoding="utf-8"`，包括：内建 `open()` 的文本模式调用、`Path.read_text()`/`Path.write_text()`、文本模式（`mode="w"` 等）的 `tempfile.NamedTemporaryFile`、以及文本模式 `os.fdopen`。二进制模式（`rb`/`wb` 等）与 `os.open` 等低层 fd 调用不受此约束。

#### Scenario: 非 UTF-8 默认 locale 下读写非 ASCII 内容

- **WHEN** 在默认编码为 cp1252 的 Windows 上，产品代码写出并读回含中文等非 ASCII 字符的文本文件（报告、JSON、Markdown、临时脚本）
- **THEN** 全程按 UTF-8 编解码，不抛 UnicodeEncodeError/UnicodeDecodeError，读回内容与写出一致

#### Scenario: Unix 行为不变

- **WHEN** 在默认 UTF-8 locale 的 macOS/Linux 上运行既有测试与命令
- **THEN** 行为与改动前一致（显式 encoding 与环境默认相同）

### Requirement: 子进程文本输出按 UTF-8 解码

产品代码中以 `text=True` 捕获子进程 stdout/stderr 的调用 SHALL 显式指定 `encoding="utf-8"`。

#### Scenario: 子进程文本捕获

- **WHEN** 产品代码以 `text=True` 调用 subprocess（git、docker、pylint 等）并解析其 stdout/stderr
- **THEN** 输出按 UTF-8 解码，不依赖平台 ANSI 代码页

### Requirement: 文本 IO 编码守护

测试套件 SHALL 包含对 src/ 的静态守护：引入无显式 encoding 的文本 IO 时测试失败。

#### Scenario: 守护测试拦截回归

- **WHEN** src/ 下任一文件出现无 `encoding=` 的文本模式 `open()`、`read_text()`、`write_text()`、文本模式 `NamedTemporaryFile`、文本模式 `fdopen` 或 `text=True` 的 subprocess 调用
- **THEN** 守护测试（tests/test_windows_utf8_io.py）断言失败并列出违规文件与行号
