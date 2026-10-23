## 修复方案
使用 Starlette HTTPConnection 解析现有 Cookie。在 Authorization 缺席时读取 ACCESS_COOKIE；存在 header 时沿用 Bearer 格式检查。两种凭据均由同一个 AuthService.authenticate 验证，认证失败仍采用原有错误响应。

## 验证
通过真实登录获得 Cookie/CSRF token，覆盖三个上传入口、私有文件下载、题库导出、结果下载；验证 header 优先级、无效 Cookie、缺失 CSRF、上传大小/限流/容量和未认证请求不读取正文。
