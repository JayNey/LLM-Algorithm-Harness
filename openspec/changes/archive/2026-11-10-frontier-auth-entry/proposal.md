## Why

登录和注册目前只有通用表单。用用户选定的 Frontier 实验入口替换认证布局，在登录前呈现工作台的品牌和策略评估用途。

## What Changes

- 登录和注册共用 Frontier 品牌区与表单区。桌面显示准确率与评估成本的前沿示意，窄屏使用紧凑品牌区和单列表单。
- 复用语言和主题选择器，支持简体中文、English、浅色和深色的独立组合。
- 在表单底部提供清晰的登录与注册互链，并保留认证交互。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/auth-session`：为登录和注册增加 Frontier 入口布局与浅深、中英文组合的验收要求。

## Impact

影响 React 认证布局、登录与注册页的呈现层及两套翻译资源。使用现有 Ant Design 组件、品牌 SVG 和外观偏好。
