---
comet_change: frontend-account-settings
role: technical-design
canonical_spec: openspec
---

# 前端账户设置 — 技术设计（Design Doc）

> 本文深化 open 阶段 `openspec/changes/frontend-account-settings/design.md`。canonical 需求以 OpenSpec delta spec 为准：`openspec/changes/frontend-account-settings/specs/frontend/user-profile/spec.md` 和 `openspec/changes/frontend-account-settings/specs/frontend/api-keys/spec.md`。

## 1. 意图

登录会话已经能守卫六个业务页。本设计把设置页接到已有的当前用户资料接口和 LLM API 密钥接口。后端契约不改。

## 2. 目标 / 非目标

**目标**

- `/settings` 只提供两个入口，页面模块不请求资料或密钥。
- 资料页展示用户名、邮箱和本地注册时间，并按注册规则修改用户名和邮箱。
- 密钥页按三个提供商分组，支持添加、改名、确认后删除和验证。
- 密钥值只在添加时经密码框输入一次。之后的类型、载荷和界面都没有密钥字段。

**非目标**

- 不替换已保存的密钥值，尽管后端 `PATCH` 可以接收新密钥。
- 不新增 HTTP 客户端，不改登录、刷新和路由守卫的判定。
- 不展示验证次数，不展示密钥明文、掩码、后四位或密文。
- 不新增 npm 依赖，不为页面引入组件测试库。

## 3. 模块

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `frontend/src/auth/registerForm.ts` | 继续导出用户名和邮箱规则，供注册和资料共用 | 无 |
| `frontend/src/account/profile.ts` | 解析资料、校验资料、把 Unix 秒格式化为本地时间 | `registerForm`、`dayjs` |
| `frontend/src/account/apiKeys.ts` | 分组、拒绝非法密钥、构造只含名称的改名载荷、验证文案 | 无 |
| `frontend/src/store/auth.ts` | 给现有客户端补上 `patch` 和 `delete`；成功改名后写回会话用户名 | 现有 `http`、`tokenStore` |
| `frontend/src/routes.tsx` | 增加不进入顶栏的两条设置子路由 | 现有懒加载 |
| `frontend/src/pages/Settings/SettingsPage.tsx` | 两个链接 | `react-router-dom` |
| `frontend/src/pages/Settings/ProfilePage.tsx` | 读取、展示和提交资料 | `profile`、会话 store、Ant Design |
| `frontend/src/pages/Settings/ApiKeysPage.tsx` | 列表、添加、改名、删除和验证 | `apiKeys`、会话 store、Ant Design |

`App.tsx` 把 `/settings/profile` 和 `/settings/api-keys` 放在现有 `RequireSession` 和 `AppLayout` 里面，放在 `appPages` 循环之外。未登录访问这两条路由时，现有守卫进入登录页，页面组件不渲染。

## 4. 纯模块契约

`validateUsername` 和 `validateEmail` 从 `registerForm.ts` 导出。`validateRegistration` 改为调用它们。规则不变：用户名 3–64 个字符，只含字母、数字、下划线、点或连字符；邮箱长度 3–254，且同时包含 `@` 和 `.`。失败文案仍是「用户名需为 3–64 个字母、数字、下划线、点或连字符」和「请输入有效邮箱」。

`readProfile` 只接受含字符串 `username`、字符串 `email` 和数字 `created_at` 的对象，否则返回 `null`。`formatUnixSeconds` 使用 `dayjs.unix(seconds).format('YYYY-MM-DD HH:mm')`，按运行环境的本地时区显示。

`readApiKey` 只复制 `id`、`provider`、`key_name`、`created_at`、`last_used_at`、`usage_count`、`verified`。响应里即使带有密钥字段，结果对象也不包含它。`readApiKeys` 在入参不是数组时返回 `null`；数组里无法识别的元素被跳过。`groupApiKeys` 只保留 `openai`、`anthropic`、`siliconflow`，并按这个顺序输出。某一组没有记录时，结果里没有该组。`last_used_at === null` 时文案为「尚未使用」，使用次数取该记录的 `usage_count`，缺省按 0。

`rejectApiKey` 在值为空白，或以 `env:`、`ENV:`、任意大小写的 `env:`、或以 `${` 开头时返回「需要真实密钥值」，否则返回 `null`。`validateKeyName` 要求 1–100 个字符，否则返回「名称需为 1–100 个字符」。`renamePayload(keyName)` 的返回值只有 `key_name`。`verifyStatusText(ok)` 只返回「验证成功」或「验证失败」。

这些纯模块使用相对导入，不引用 `import.meta` 或 `@/`。

## 5. 数据流

客户端继续使用 `VITE_API_BASE_URL` 作为 axios `baseURL`。页面请求路径是 `/users/me`、`/api-keys`、`/api-keys/{id}` 和 `/api-keys/{id}/verify`。响应拦截器已经解开 `data`，204 变成 `undefined`。

资料页打开后先显示「加载中」。`GET /users/me` 成功且 `readProfile` 成功时填表，并显示本地注册时间。解析失败或请求失败时只显示错误，不渲染资料字段。提交前先跑 `validateProfile`，有错误则不发请求。通过后 `PATCH /users/me`，正文是 `{ username, email }`。成功后用响应更新表单；用户名与当前会话不同时调用 store 的 `updateUsername`，把新用户名写回当前使用的那一种浏览器存储。

密钥页打开后 `GET /api-keys`。添加表单包含提供商选择、名称和 `type="password"` 的密钥框。客户端拒绝非法名称或密钥时不发请求。成功的 `POST /api-keys` 正文是 `{ provider, key_name, api_key }`。成功后清空三个输入并重新拉取列表。列表组件的 props 类型使用 `ApiKeyRecord`，因此没有密钥值可渲染。页上保留说明「密钥保存后不再显示」。

改名只调用 `renamePayload`，再 `PATCH /api-keys/{id}`。删除先用 Ant Design `Modal.confirm`。取消不发请求。确认后才 `DELETE`。验证对当前记录单独显示加载。`POST /api-keys/{id}/verify` 返回后，无论 `ok` 为何，都重新拉取列表；提示只用 `verifyStatusText`，不读取响应里的 `message` 或 `provider`。

`AuthClient` 增加 `patch` 和 `delete`。运行时仍是现有 axios 实例，不创建第二个客户端。

## 6. 错误处理

沿用会话客户端已经映射的状态码。页面使用下面这些原句，不直接展示后端英文 `detail`：

- 资料 409：显示「用户名或邮箱不可用」，保留用户名和邮箱。
- 400 且没有可对应到字段的 `details`：显示「请求无效」。
- 429：显示「请求过于频繁，请稍后再试」。
- 网络错误和 5xx：显示「服务暂时不可用」。
- 验证失败：显示「验证失败」。
- 验证成功：显示「验证成功」，并把该记录显示为已验证。
- 没有密钥：显示「还没有 API 密钥」。
- 资料保存成功：显示「已保存」。

401 仍由现有拦截器刷新或进入登录页。资料加载失败时不保留上一份资料。

## 7. 测试

`frontend/package.json` 的 `test` 脚本继续使用 `node --experimental-strip-types --test`，并加上 `src/account/*.test.ts`。不新增依赖。

- `profile`：非法对象不被当成资料；Unix 秒格式化结果包含公历年份而不是只剩整数。
- `apiKeys`：OpenAI 与 Anthropic 分到对应组，空的 SiliconFlow 组不出现；`last_used_at` 为空时文案是「尚未使用」且使用次数为 0。
- `apiKeys`：空白、`env:`、`ENV:` 和 `${` 开头的值被拒绝。
- `apiKeys`：`renamePayload` 的键只有 `key_name`；验证文案只有成功或失败两句。

页面不写组件测试。完成标准是在 `frontend/` 中类型检查、`npm run lint` 和生产构建都成功退出，并且 `npm test` 通过。

## 8. 风险

- 顶栏用户名来自登录时写入的会话。资料页改名后必须写回会话，否则顶栏会继续显示旧用户名。
- 改名请求多带 `api_key` 会让后端清除已验证状态。载荷函数不接受密钥参数。
- 验证接口可能慢或返回 429。只有被点击的那条记录进入加载，失败文案使用第 6 节的原句。
- 本分支在设计前已经合并 `main` 上的登录会话实现。设置页不再等待那份客户端单独编码。
