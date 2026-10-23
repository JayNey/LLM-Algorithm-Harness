## 问题与根因
文件上传、题库上传、配置上传和文件/结果下载、题库导出的文件边界中间件只读取 Bearer header；项目现有 current_user 已支持 HttpOnly access Cookie，因此正常浏览器会话被提前返回 401。

## 修复目标
边界接受既有 Cookie access token；显式 Authorization 始终优先，不允许无效 header 回退 Cookie。认证仍先于读取正文、占用传输容量，CSRF、上传限流与所有权校验保持有效。不新增 capability 或 public API。

## 复现证据（RED）
运行 `pytest tests/test_api_files.py -k 'cookie_session or file_boundary' -o addopts='' -q --tb=line`：5 failed、3 passed。三个真实登录 Cookie 上传入口均返回 401（预期 201/200/201），Cookie 私有下载返回 401（预期 200），合法 Cookie 的大小限制场景返回 401（预期 413）。修复后同一组 8 passed。
