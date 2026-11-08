# Tasks

- [x] 1. 抽出 `statusPolling.ts` 会话（终态/403/404 停止、暂时性故障续跑、dispose 隔离）
- [x] 2. 单元测试覆盖成功/终态/5xx/断网/403/404/恢复/dispose 九个场景（先 RED 后 GREEN）
- [x] 3. `useStatusPolling` 适配会话并公开 error/fatal/reload
- [x] 4. 详情页接入：错误 + 过期标注 + 重试；fatal 清除过期状态与操作入口
- [x] 5. i18n 键补齐 zh-CN/en-US 并通过资源一致性测试
- [x] 6. `npm test`（331）、`tsc -b`、`eslint`、`prettier format:check` 全绿
- [x] 7. 同步主 spec `frontend/abtest-management`
