# 验证证据

- RED：`pytest tests/test_api_files.py -k 'cookie_session or file_boundary' -o addopts='' -q --tb=line`，5 failed / 3 passed；5 项失败均为 Cookie 请求被文件边界提前返回 401。
- GREEN：同组测试，8 passed / 61 deselected。
- `python3 -m compileall -q api`：退出码 0。
- `black --check api/files/middleware.py tests/test_api_files.py`：退出码 0。
- `ruff check api/files/middleware.py tests/test_api_files.py`：退出码 0。
- `git diff --check`：退出码 0。
- 根因消除：边界在 Authorization 缺席时读取既有 ACCESS_COOKIE，两种 token 均经相同 authenticate 验证；显式空/错误 Authorization 不回退 Cookie；认证仍发生在传输容量租用和正文读取之前，上传限流仍在认证后执行。CSRF 中间件顺序与路由所有权验证均未更改。
- Comet context 插件因全局 state.json.lock 的文件权限限制未加载；按 hotfix 协议插件失败不阻断修复。

- 相关测试：`pytest tests/test_api_files.py tests/test_api_auth.py tests/test_api_errors.py -o addopts='' -q --tb=short`：166 passed，5 条已有 Pydantic 弃用警告。未运行全仓库测试或覆盖率门槛。
