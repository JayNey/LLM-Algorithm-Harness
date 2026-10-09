# Tasks: windows-utf8-encoding

## 1. 修复存量编码点（src/ 5 文件 13 处）

- [x] 1.1 `src/code_quality/readability_analyzer.py`：3 处 `NamedTemporaryFile(mode="w")`（L65/L94/L116）与 3 处 subprocess（pylint L69/flake8 L98/radon L120）补 `encoding="utf-8"`；验证：语句级扫描该文件零命中
- [x] 1.2 `src/code_quality/style_analyzer.py`：1 处 `NamedTemporaryFile`（L67）与 1 处 subprocess（black L71）补 `encoding="utf-8"`；验证：同上
- [x] 1.3 `src/experiment.py`：2 处 git subprocess（L49/L63）补 `encoding="utf-8"`；验证：同上
- [x] 1.4 `src/sandbox_executor.py`：2 处 docker subprocess（L203/L214）补 `encoding="utf-8"`；验证：同上
- [x] 1.5 `src/main.py`：L2252 `read_text()` 补 `encoding="utf-8"`；验证：同上

## 2. 守护测试

- [x] 2.1 新增 `tests/test_windows_utf8_io.py`：AST 扫描 src/**/*.py，文本模式 open/read_text/write_text/NamedTemporaryFile(w)/fdopen 与 text=True subprocess 必须显式 `encoding=`，bytes 模式与低层 fd 豁免；验证：`pytest tests/test_windows_utf8_io.py -v` 通过（并当场抓到语句级扫描漏掉的 sandbox_executor.py:545，已补修）
- [x] 2.2 变异验证守护有效：临时移除任一处 `encoding=` 确认守护测试变红，再恢复；验证：观察到红→绿（experiment.py git 调用为变异样本）

## 3. 回归验证

- [x] 3.1 `black --check .` 与 `ruff check .` 全绿；验证：两命令退出码均为 0（188 文件无格式改动）
- [x] 3.2 `pytest -m "not online" -q` 全量通过，覆盖率 ≥ 90（门禁原样）；验证：1104 passed / 4 skipped，coverage 90.70%
