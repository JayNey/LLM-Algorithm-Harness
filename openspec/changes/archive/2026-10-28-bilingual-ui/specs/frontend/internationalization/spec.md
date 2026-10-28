## ADDED Requirements

### Requirement: 中英文界面资源

系统 SHALL 使用国际化框架提供 zh-CN 和 en-US 翻译资源，覆盖应用提供的导航、认证、业务页面、表单、状态、反馈与设置文案。业务标识、代码、用户输入和服务端内容 SHALL 保持原值。

#### Scenario: 英文界面
- **WHEN** 用户选择 English
- **THEN** 当前页面及后续路由的前端文案呈现英文，动态值正确插值且不作为 HTML 执行

#### Scenario: 中文回切
- **WHEN** 用户从英文切回简体中文
- **THEN** 导航、页面、校验提示与公共反馈恢复中文

### Requirement: 即时语言选择

系统 SHALL 在认证页和已登录工作台提供具有可访问名称且支持键盘的语言选择器。切换语言 SHALL 不改变当前路由、不重新挂载业务页面、不清空输入，也不重启业务任务。

#### Scenario: 保持输入
- **WHEN** 用户输入表单内容后切换语言
- **THEN** 表单值与当前路由保留，界面文案立即更新

### Requirement: 偏好持久化与安全降级

系统 SHALL 保存显式语言选择并在刷新后恢复。无偏好、非法或损坏的存储值 SHALL 默认 zh-CN。存储不可读写 SHALL 不阻止应用加载和内存中的语言切换。

#### Scenario: 刷新恢复
- **WHEN** 用户选择 English 后刷新
- **THEN** 首次呈现使用 en-US

#### Scenario: 不可用存储
- **WHEN** 浏览器拒绝本地存储访问
- **THEN** 应用默认使用中文并允许当前会话切换为英文

### Requirement: 语言环境一致

系统 SHALL 同步 Ant Design 组件、dayjs 和 HTML lang 的语言环境，应用生成的日期与数字呈现 SHALL 使用当前界面语言。

#### Scenario: 组件和页面语义
- **WHEN** 用户切换到 en-US
- **THEN** 组件库内置文案和日期环境使用英文，document.documentElement.lang 为 en-US
