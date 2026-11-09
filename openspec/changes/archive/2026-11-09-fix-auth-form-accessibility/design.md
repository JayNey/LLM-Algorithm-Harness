## Context

认证页面由 Ant Design 提供标签与错误提示的布局，由 React Hook Form 管理输入与校验。Form.Item 外层没有注册 Ant Design 字段，实际输入位于 Controller 的 render 回调中，因此需要显式关联标签与校验提示。

## Goals / Non-Goals

在输入层提供中英文名称与对应字段的错误描述，沿用现有校验、焦点、提交和翻译逻辑。

## Decisions

- 使用 Form.Item 的 `htmlFor` 指向现有输入 ID。
- 将输入的 `aria-describedby` 指向可见校验提示，字段有错误时设置 `aria-invalid`。
- 在 CI 已运行的生产构建冒烟中读取 Chromium 可访问树，并从表单的默认焦点开始通过 Tab 和 Enter 操作。

## Risks / Trade-offs

密码输入的可访问名称也通过 Chromium 可访问树验证。320px 检查同时覆盖错误展开后的页面宽度。
