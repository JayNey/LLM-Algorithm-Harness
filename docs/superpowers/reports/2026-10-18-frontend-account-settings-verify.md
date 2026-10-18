# 验证报告：frontend-account-settings

**日期**: 2026-10-18  
**变更名称**: frontend-account-settings  
**验证模式**: full  
**产物语言**: zh-CN  
**范围**: `4654f3c384b17d8ff73d80a581159d2724289e40..f8ebba01450fcd2e45f905b4ad1297756d95cf85`  
**分支**: `comet/frontend-account-settings`

## Summary

| Dimension | Status |
| --- | --- |
| Completeness | 7/7 tasks，2 份 delta spec |
| Correctness | 资料与密钥需求已实现；一次集成审查的 Important 已在 `f8ebba0` 修复并复审通过 |
| Coherence | 实现遵循技术设计；OpenSpec `design.md` 里“展示接口返回的通用消息”由技术设计第 6 节和 delta spec 收成「验证失败」 |

## 完整性

`openspec/changes/frontend-account-settings/tasks.md` 的 1.1、1.2、1.3、2.1、2.2、2.3、3.1 都是 `[x]`。计划 `docs/superpowers/plans/2026-10-18-frontend-account-settings.md` 的任务和步骤复选框都已勾选。

改动落在设置入口、资料页、密钥页、`frontend/src/account`、注册规则抽取和会话客户端的 `patch` / `delete`。没有新增 npm 依赖，没有改后端。

## 正确性

| 需求 | 证据 |
| --- | --- |
| 设置页只提供两个入口 | `frontend/src/pages/Settings/SettingsPage.tsx` 只有「个人资料」和「API 密钥」两个链接 |
| 资料读取、本地时间和失败不展示资料 | `ProfilePage.tsx` 在加载时显示「加载中」，失败时只显示错误 |
| 用户名和邮箱规则，409 保留表单 | `validateProfile` 复用注册规则；409 显示「用户名或邮箱不可用」 |
| 未登录进入登录页 | 两条子路由在现有 `RequireSession` 内，`RequireSession.tsx` 导向 `/login` |
| 三个提供商分组，空组不出现，尚未使用 | `groupApiKeys`、`lastUsedLabel`，Node 测试覆盖 |
| 密码框添加，拒绝空白、`env:` 和 `${` | `Input.Password` 与 `rejectApiKey` |
| 改名载荷只有 `key_name` | `renamePayload`，测试断言不含 `api_key` |
| 删除先确认 | `Modal.confirm`，请求在 `onOk` 内 |
| 验证只显示成功或失败 | `verifyStatusText`，不读取 `message` |
| 400 / 429 / 其他失败文案 | `requestFailureText`：400「请求无效」，429「请求过于频繁，请稍后再试」，其余「服务暂时不可用」 |

`verified` 接受布尔或整数 0/1，列表类型不保留 `api_key`。

## 集成审查

审查范围是上述基线到修复前的前端 diff。没有 Critical。

Important：添加密钥把 `POST` 和随后的列表刷新放在同一个失败分支，400 也被写成「服务暂时不可用」。修复提交 `f8ebba0` 把 400 映射为「请求无效」，`POST` 失败时保留表单且不刷新，成功后才清空并单独刷新。复审结论为 Approved。

未阻塞的 Minor：资料接口返回 400 时，页面显示「请求无效」，没有把 `details` 写回具体字段。密钥列表刷新失败时，页面改为错误视图，并保留已有的验证提示。这两项不改变规格要求的成功路径。

## 检查命令

在 `frontend/` 于修复提交之后重新执行，退出码 0：

```text
./node_modules/.bin/tsc -b --pretty false && npm run lint && npm test && npm run build
```

`npm test` 为 76 pass / 0 fail / 0 skipped。其中包含分组、非法密钥值、改名载荷和 400 文案。`npm warn Unknown env config "devdir"` 是环境噪音。

## 安全

页面不渲染密钥值。添加框是密码输入。请求路径相对 `VITE_API_BASE_URL`，没有新增第二套 HTTP 客户端，也没有硬编码密钥。

## Final Assessment

没有未修复的 Critical 或 Important。可以进入归档。
