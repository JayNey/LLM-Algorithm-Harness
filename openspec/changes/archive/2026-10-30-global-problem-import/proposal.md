## Why

工作台各处的全局“导入题目”操作仍打开明确标记为 Mock 的示例弹窗；用户无法从这些入口开始个人题库的真实导入。题库页已经具备文件选择、同步/异步导入、进度和校验报告，应让全局入口复用这一流程。

## What Changes

- 将桌面侧栏、顶部快速操作和移动导航中的导入入口导航到题库页，并自动展开真实导入面板。
- 移除全局入口使用的 Mock 导入弹窗，不改其他页面仍在使用的 Mock 组件。
- 保留现有文件格式、导入模式、大小阈值、异步进度和结果反馈，并补齐中英文与键盘可访问反馈。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell`：全局导入入口改为进入真实题库导入流程；其他 Mock 区域仍按区域明确标注。
- `frontend/problems-management`：保持现有导入契约，并覆盖取消选择、重复提交和会话切换时的安全边界。

## Impact

- 影响 `frontend/src/layouts/AppLayout.tsx`、导航组件、题库页面和中英文资源。
- 复用现有 ProblemsPage 导入客户端和 API；不增加后端接口或改变上传及异步任务协议。

## 联合交付

用户于 2026-10-28 确认 #298、#299、#301 一起实现并提交同一 PR。报告下载和提示文案分别由同分支的 `evaluation-report-downloads` 与 `budget-import-guidance` OpenSpec 产物描述。
