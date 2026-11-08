## ADDED Requirements

### Requirement: 生产 Web 入口

生产编排 SHALL 在 Nginx 的公开入口提供构建后的 Web 应用和同源 API 与 WebSocket。页面导航 SHALL 支持 SPA 深链接，入口 HTML SHALL 可重新验证，缺失的静态分包 SHALL 返回 404。业务 API 与 WebSocket 握手 SHALL 保持现有的就绪准入语义。

#### Scenario: 访问登录页与刷新深链接

- **WHEN** 浏览器通过发布入口访问 `/login` 或硬刷新业务深链接
- **THEN** 返回 SPA HTML，浏览器可以加载入口和路由分包，缺失的静态分包返回 404

#### Scenario: 同源会话和进度连接

- **WHEN** 用户通过发布入口登录
- **THEN** 浏览器收到会话 Cookie，后续同源 API 与进度 WebSocket 使用该会话成功鉴权

#### Scenario: API 未就绪后恢复

- **WHEN** API 未就绪或暂时不可达
- **THEN** SPA 与分包仍可访问，业务 API 与新 WebSocket 握手返回 503，API 恢复就绪后新请求重新通过准入
