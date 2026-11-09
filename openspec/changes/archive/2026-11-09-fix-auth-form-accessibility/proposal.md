## Why

[#429](https://github.com/JayNey/LLM-Algorithm-Harness/issues/429) 发现登录与注册表单的视觉标签和错误提示缺少输入关联，辅助技术无法据此识别字段和校验错误。

## What Changes

- 为登录与注册的六个字段关联中英文可见标签和各自的校验错误。
- 在现有 Chromium 冒烟中覆盖 320px 下的可访问名称、错误描述、Tab 导航和回车提交。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/auth-session` 更新认证表单的可访问性验收场景。

## Impact

涉及登录页、注册页和现有生产构建浏览器冒烟。
