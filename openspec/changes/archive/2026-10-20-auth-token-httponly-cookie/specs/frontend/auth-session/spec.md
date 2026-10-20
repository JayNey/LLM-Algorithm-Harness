## MODIFIED Requirements

### Requirement: 受保护请求携带访问令牌

已登录状态下发往本应用 API 的请求 SHALL 携带浏览器保存的访问令牌 cookie，且 MUST NOT 由页面脚本设置 `Authorization` 头，也 MUST NOT 把访问令牌或刷新令牌写入 Web Storage。注册、登录和刷新请求 MUST NOT 依赖已有访问令牌。访问令牌缺失、过期或被拒绝时，若浏览器仍有刷新令牌 cookie，客户端 SHALL 只发起一次刷新并在成功后重试原来的请求一次。同一时刻多个请求需要刷新时 SHALL 共用这一次刷新。刷新失败或没有可恢复会话时，客户端 SHALL 清除本地会话标记并进入登录页。

#### Scenario: 请求自动带上访问令牌

- **WHEN** 已登录用户触发一个受保护 API 请求
- **THEN** 该请求允许浏览器附带访问令牌 cookie，且页面脚本没有设置 Bearer 认证头

#### Scenario: 访问令牌过期后刷新

- **WHEN** 受保护请求因 access token 无效被拒绝，且刷新令牌 cookie 仍有效
- **THEN** 客户端刷新会话，并成功重试原来的请求一次

#### Scenario: 刷新失败

- **WHEN** 刷新请求被拒绝
- **THEN** 本地会话标记被清除，用户进入登录页

### Requirement: 登出

已登录用户 SHALL 能从导航发起登出。登出时客户端 SHALL 请求撤销当前登录会话，清除本地会话标记，然后进入登录页。撤销请求失败时，本地会话标记仍 MUST 被清除。

#### Scenario: 登出成功

- **WHEN** 已登录用户选择登出且撤销请求成功
- **THEN** 本地会话标记消失，页面进入登录页，后续受保护页面不再直接打开

#### Scenario: 撤销请求失败仍退出

- **WHEN** 已登录用户选择登出且撤销请求失败
- **THEN** 本地会话标记仍然消失，页面进入登录页
