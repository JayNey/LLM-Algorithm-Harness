# 贡献指南

感谢您对 LLM Algorithm Harness 的贡献！本文档提供了项目的开发规范和最佳实践。

## 路径处理规范

为确保跨平台兼容性（macOS、Linux、Windows），请遵循以下路径处理规范：

### 使用 `pathlib.Path` 处理文件系统路径

**必须：** 所有文件系统路径操作使用 `pathlib.Path`，而非字符串拼接或 `os.path`。

```python
# ✅ 正确
from pathlib import Path

data_dir = Path("data")
problem_file = data_dir / "problems.json"

# ❌ 错误
data_dir = "data"
problem_file = data_dir + "/problems.json"  # 在 Windows 上会失败
```

`pathlib.Path` 自动使用平台正确的路径分隔符（Unix 上是 `/`，Windows 上是 `\`）。

### URL 和文本解析中的正斜杠

**重要：** URL 路径解析和文本分隔符中的正斜杠（`/`）是正确的，不要替换为 `os.sep` 或 `Path`。

```python
# ✅ 正确 - URL 路径解析
from urllib.parse import urlparse

parsed = urlparse("https://leetcode.com/problems/two-sum/")
parts = parsed.path.split("/")  # 正斜杠是 RFC 3986 URL 路径分隔符

# ✅ 正确 - 文本解析
score_text = "Your code has been rated at 8.5/10"
score = float(score_text.split("/")[0].split()[-1])  # 正斜杠是文本分隔符

# ❌ 错误
parts = parsed.path.split(os.sep)  # 在 Windows 上会失败
```

### 避免 Windows 保留文件名

测试数据和临时文件不得使用 Windows 保留设备名称（不区分大小写，带或不带扩展名）：

- `CON`, `PRN`, `AUX`, `NUL`
- `COM1` 至 `COM9`
- `LPT1` 至 `LPT9`

```python
# ✅ 正确 - 使用 tempfile 模块
import tempfile

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    f.write(data)  # tempfile 自动避免保留名称

# ✅ 正确 - 明确避免保留名称
test_files = ["input1.txt", "output1.txt", "test_data.json"]  # 安全的文件名

# ❌ 错误
test_file = "CON.txt"  # Windows 上会失败（"拒绝访问"错误）
```

### 大小写敏感性

**不要假设：** 文件系统是大小写敏感的。

- Linux：通常大小写敏感
- macOS：默认大小写不敏感（APFS 可配置为大小写敏感）
- Windows：大小写不敏感

```python
# ✅ 正确 - 使用 Path 对象比较
from pathlib import Path

path1 = Path("data/problems.json")
path2 = Path("data") / "problems.json"
assert path1 == path2  # Path 对象正确处理平台差异

# ✅ 正确 - 文件存在性检查
if Path("README.md").exists():
    ...  # 在所有平台上正常工作

# ❌ 错误 - 假设大小写敏感
if "README.md" in os.listdir("."):
    ...  # 可能在大小写不敏感的系统上失败
```

## 测试

运行测试前，确保安装开发依赖：

```bash
pip install -e ".[dev]"
pytest
```

## 代码风格

本项目使用以下工具保持代码风格一致：

- **格式化：** `black`
- **导入排序：** `isort`
- **类型检查：** `mypy`

在提交前运行：

```bash
black src/ tests/
isort src/ tests/
mypy src/
```

## 提交信息

使用清晰的提交信息：

```
feat: 添加批量导入功能
fix: 修复 Windows 路径处理问题
docs: 更新 API 文档
test: 添加增量历史测试
```

## Pull Request

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/my-feature`
3. 提交更改：`git commit -am 'feat: add my feature'`
4. 推送分支：`git push origin feature/my-feature`
5. 创建 Pull Request

感谢您的贡献！
