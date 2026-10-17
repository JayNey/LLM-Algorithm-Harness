---
change: frontend-auth-session
design-doc: docs/superpowers/specs/2026-10-17-frontend-auth-session-design.md
base-ref: c4a019c0843a2e96c32c09eb67bc363c4a2012ee
---

# 前端登录会话 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让未登录用户进入登录页，登录后带着可刷新的 Bearer 会话访问现有六个页面。

**Architecture:** `returnPath`、`tokenStore` 和 `refreshCoordinator` 是不依赖 Vite 的纯模块。唯一的 axios 实例负责认证头和单次刷新。Zustand 保存会话。公开路由与业务路由分开。

**Tech Stack:** React 18、React Router 7、Ant Design、Zustand、axios、react-hook-form、Node 自带测试运行器。

**Spec:** `docs/superpowers/specs/2026-10-17-frontend-auth-session-design.md`

## Global Constraints

- 产物语言：zh-CN。界面错误文案使用设计文档第 6 节的原句。
- 不新增 npm 依赖。
- 不解析 JWT，不把 token 写入 cookie 或 URL。
- 不实现资料编辑、API 密钥、改密码、头像和角色权限。
- 不提交 `openspec/changes/frontend-account-settings/`。
- 纯模块不得 import `import.meta` 或 `@/`。
- 登录、注册和刷新请求不附带 access token，也不进入自动刷新。登出请求附带当前 access token；access token 将过期或登出得到 401 时，先走同一次刷新再重试登出一次。

---

### Task 1: 站内回跳路径

对应 `tasks.md` 1.1。

**Files:**
- Create: `frontend/src/auth/returnPath.ts`
- Test: `frontend/src/auth/returnPath.test.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: 无
- Produces: `sanitizeReturnPath(value: string | null | undefined): string`

- [x] **Task 1 Step 1: Write the failing test**

```ts
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sanitizeReturnPath } from './returnPath.ts'

test('保留站内题目路径', () => {
  assert.equal(sanitizeReturnPath('/problems'), '/problems')
})

test('拒绝外站地址和协议相对地址', () => {
  assert.equal(sanitizeReturnPath('https://evil.example/steal'), '/')
  assert.equal(sanitizeReturnPath('//evil.example'), '/')
  assert.equal(sanitizeReturnPath(null), '/')
})
```

- [x] **Task 1 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/returnPath.test.ts`
Expected: FAIL，找不到 `./returnPath.ts`

- [x] **Task 1 Step 3: Write minimal implementation**

```ts
export function sanitizeReturnPath(value: string | null | undefined): string {
  if (value === null || value === undefined || !value.startsWith('/') || value.startsWith('//')) {
    return '/'
  }
  if (value.includes('://') || value.includes('\\')) {
    return '/'
  }
  return value
}
```

在 `frontend/package.json` 的 `scripts` 增加：

```json
"test": "node --experimental-strip-types --test src/auth/*.test.ts"
```

- [x] **Task 1 Step 4: Run test to verify it passes**

Run: `cd frontend && node --experimental-strip-types --test src/auth/returnPath.test.ts`
Expected: PASS

- [x] **Task 1 Step 5: Commit**

```bash
git add frontend/src/auth/returnPath.ts frontend/src/auth/returnPath.test.ts frontend/package.json
git commit -m "$(cat <<'EOF'
让登录回跳只接受站内路径。

EOF
)"
```

### Task 2: 记住我的存储

对应 `tasks.md` 1.2。

**Files:**
- Create: `frontend/src/auth/tokenStore.ts`
- Test: `frontend/src/auth/tokenStore.test.ts`

**Interfaces:**
- Consumes: 无
- Produces:
  - `StoredSession = { accessToken: string; refreshToken: string; expiresAt: number; username: string | null }`
  - `writeSession(remember: boolean, session: StoredSession, storages?: SessionStorages): void`
  - `readSession(storages?: SessionStorages): StoredSession | null`
  - `clearSession(storages?: SessionStorages): void`

- [x] **Task 2 Step 1: Write the failing test**

```ts
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clearSession, readSession, writeSession, type StoredSession } from './tokenStore.ts'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  }
}

const session: StoredSession = {
  accessToken: 'access',
  refreshToken: 'refresh',
  expiresAt: 1_700_000_000_000,
  username: null,
}

test('记住我只写入 localStorage', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  assert.equal(readSession(storages)?.accessToken, 'access')
  assert.equal(storages.session.length, 0)
})

test('不记住我只写入 sessionStorage，恢复时不读旧的 localStorage', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  writeSession(false, { ...session, accessToken: 'tab' }, storages)
  assert.equal(readSession(storages)?.accessToken, 'tab')
  assert.equal(storages.local.length, 0)
})

test('清除两边后不能恢复', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  clearSession(storages)
  assert.equal(readSession(storages), null)
})
```

- [x] **Task 2 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/tokenStore.test.ts`
Expected: FAIL，找不到模块

- [x] **Task 2 Step 3: Write minimal implementation**

```ts
const storageKey = 'llm-harness-session'

export interface StoredSession {
  accessToken: string
  refreshToken: string
  expiresAt: number
  username: string | null
}

export interface SessionStorages {
  local: Storage
  session: Storage
}

function browserStorages(): SessionStorages {
  return { local: localStorage, session: sessionStorage }
}

function parse(raw: string | null): StoredSession | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as StoredSession
    if (!value.accessToken || !value.refreshToken || typeof value.expiresAt !== 'number') return null
    return value
  } catch {
    return null
  }
}

export function writeSession(remember: boolean, session: StoredSession, storages: SessionStorages = browserStorages()): void {
  const selected = remember ? storages.local : storages.session
  const other = remember ? storages.session : storages.local
  selected.setItem(storageKey, JSON.stringify(session))
  other.removeItem(storageKey)
}

export function readSession(storages: SessionStorages = browserStorages()): StoredSession | null {
  return parse(storages.local.getItem(storageKey)) ?? parse(storages.session.getItem(storageKey))
}

export function clearSession(storages: SessionStorages = browserStorages()): void {
  storages.local.removeItem(storageKey)
  storages.session.removeItem(storageKey)
}
```

- [x] **Task 2 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: returnPath 与 tokenStore 测试 PASS

- [x] **Task 2 Step 5: Commit**

```bash
git add frontend/src/auth/tokenStore.ts frontend/src/auth/tokenStore.test.ts
git commit -m "$(cat <<'EOF'
按记住我把会话写入一种浏览器存储。

EOF
)"
```

### Task 3: HTTP 客户端与过期前刷新

对应 `tasks.md` 2.1。

**Files:**
- Create: `frontend/src/auth/http.ts`
- Test: `frontend/src/auth/http.test.ts`

**Interfaces:**
- Consumes: `StoredSession`、`readSession`、`writeSession`
- Produces:
  - `isAuthEndpoint(url: string): boolean`
  - `shouldRefreshBeforeRequest(expiresAt: number, now: number): boolean`
  - `ApiClientError`
  - `createHttpClient(options): AxiosInstance`

- [x] **Task 3 Step 1: Write the failing test**

测试用 axios 的 `adapter` 记录请求，不访问网络。

```ts
test('受保护请求带 Bearer', async () => {
  const seen: string[] = []
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => ({ accessToken: 'access', refreshToken: 'refresh', expiresAt: 60_000, username: 'ada' }),
    write: () => undefined,
    clear: () => undefined,
    refresh: async () => {
      throw new Error('不应刷新')
    },
    adapter: (config) => {
      seen.push(config.headers?.Authorization ?? '')
      return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: { success: true, data: { ok: true }, message: '' } })
    },
  })
  await client.get('/api/v1/users/me')
  assert.equal(seen[0], 'Bearer access')
})

test('登录请求不刷新', async () => {
  let refreshed = false
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => ({ accessToken: 'old', refreshToken: 'refresh', expiresAt: 0, username: null }),
    write: () => undefined,
    clear: () => undefined,
    refresh: async () => {
      refreshed = true
      return { accessToken: 'new', refreshToken: 'next', expiresAt: 60_000, username: null }
    },
    adapter: (config) => Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: { success: true, data: {}, message: '' } }),
  })
  await client.post('/api/v1/auth/login', { username: 'ada', password: 'secret' })
  assert.equal(refreshed, false)
})
```

同样断言 `/auth/register`、`/auth/refresh`、`/auth/logout` 不调用 `refresh`，并且请求头没有 `Authorization`。再加一条：受保护请求的 `expiresAt` 距 `now` 不足 30 秒时，先调用 `refresh`，再用新 access token 发原请求。

- [x] **Task 3 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/http.test.ts`
Expected: FAIL，找不到 `createHttpClient`

- [x] **Task 3 Step 3: Write minimal implementation**

`isAuthEndpoint` 在去掉 query 后判断路径是否以这四段结尾。`shouldRefreshBeforeRequest` 在 `expiresAt - now < 30_000` 时返回 true。请求拦截器对非认证端点、且会话将在 30 秒内过期时先 `refresh`，然后设置 Bearer。成功响应返回 `data` 字段。状态码不是 2xx 时抛出 `ApiClientError`，消息优先取 `detail`，其次 `message`。204 返回 `undefined`。

- [x] **Task 3 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [x] **Task 3 Step 5: Commit**

```bash
git add frontend/src/auth/http.ts frontend/src/auth/http.test.ts
git commit -m "$(cat <<'EOF'
给受保护请求附上访问令牌。

EOF
)"
```

### Task 4: 单次刷新

对应 `tasks.md` 2.2。

**Files:**
- Create: `frontend/src/auth/refreshCoordinator.ts`
- Test: `frontend/src/auth/refreshCoordinator.test.ts`
- Modify: `frontend/src/auth/http.ts`
- Modify: `frontend/src/auth/http.test.ts`

**Interfaces:**
- Consumes: `createHttpClient`
- Produces: `createRefreshCoordinator<T>(run: () => Promise<T>): { refresh(): Promise<T> }`

- [x] **Task 4 Step 1: Write the failing test**

```ts
test('并发刷新只执行一次', async () => {
  let calls = 0
  const coordinator = createRefreshCoordinator(async () => {
    calls += 1
    await new Promise((resolve) => setTimeout(resolve, 10))
    return 'next'
  })
  const [first, second] = await Promise.all([coordinator.refresh(), coordinator.refresh()])
  assert.equal(calls, 1)
  assert.equal(first, 'next')
  assert.equal(second, 'next')
})
```

在 `http.test.ts` 增加：两个并发请求都收到 401，adapter 对刷新地址返回新 token，对原请求第二次返回 200。断言刷新地址只出现一次，两个原请求最终成功。刷新失败时调用 `clear`。

- [x] **Task 4 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/refreshCoordinator.test.ts src/auth/http.test.ts`
Expected: FAIL，协调器不存在；HTTP 测试中两次 401 各自刷新

- [x] **Task 4 Step 3: Write minimal implementation**

`createRefreshCoordinator` 保存一个 `inflight`。存在时返回它；`finally` 里清空。`http` 的 401 拦截器对非认证端点调用这个协调器，成功后用新 access token 重试原请求一次。用 `config.__retried` 防止第二次 401 再刷新。刷新失败调用 `clear` 并抛出 `ApiClientError`。

- [x] **Task 4 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [x] **Task 4 Step 5: Commit**

```bash
git add frontend/src/auth/refreshCoordinator.ts frontend/src/auth/refreshCoordinator.test.ts frontend/src/auth/http.ts frontend/src/auth/http.test.ts
git commit -m "$(cat <<'EOF'
把并发的访问令牌刷新合并成一次。

EOF
)"
```

### Task 5: 认证 store

对应 `tasks.md` 2.3。

**Files:**
- Create: `frontend/src/store/auth.ts`
- Test: `frontend/src/store/auth.test.ts`

**Interfaces:**
- Consumes: `StoredSession`、`writeSession`、`readSession`、`clearSession`、`createHttpClient`
- Produces: `useAuthStore`，含 `session`、`hydrate()`、`login(identity, password, remember)`、`logout()`、`clear()`

- [x] **Task 5 Step 1: Write the failing test**

用注入的 client 替身，不创建真实 axios。`login` 依次调用 login 和 `/users/me`。`clear` 后 `readSession` 返回 null。

```ts
test('清除后不能恢复会话', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, { accessToken: 'a', refreshToken: 'r', expiresAt: 10, username: 'ada' }, storages)
  clearSession(storages)
  assert.equal(readSession(storages), null)
})
```

store 测试断言 `login` 收到 `{ access_token, refresh_token, expires_in: 30 }` 后，写入的 `expiresAt` 等于 `now + 30000`，并且随后读取了 `/users/me`。

- [x] **Task 5 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/store/auth.test.ts`
Expected: FAIL，找不到 store

- [x] **Task 5 Step 3: Write minimal implementation**

`hydrate` 调用 `readSession`。`login` 调 `POST /api/v1/auth/login`，写入 token，再 `GET /api/v1/users/me`；资料失败且不是 401 时保留 token 并把 `username` 留空。`logout` 用 try/finally 包住 `POST /api/v1/auth/logout`，finally 中 `clearSession` 并把 store 设为 null。测试通过可选依赖注入 client 和 storages。

- [x] **Task 5 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [x] **Task 5 Step 5: Commit**

```bash
git add frontend/src/store/auth.ts frontend/src/store/auth.test.ts
git commit -m "$(cat <<'EOF'
保存登录会话并在退出时清除它。

EOF
)"
```

### Task 6: 注册页

对应 `tasks.md` 3.1。

**Files:**
- Create: `frontend/src/auth/registerForm.ts`
- Test: `frontend/src/auth/registerForm.test.ts`
- Create: `frontend/src/pages/Auth/RegisterPage.tsx`

**Interfaces:**
- Consumes: `createHttpClient` 的生产实例 `http`
- Produces:
  - `passwordStrength(password: string): 'short' | 'ok' | 'long'`
  - `validateRegistration(input): Record<string, string>`

- [x] **Task 6 Step 1: Write the failing test**

```ts
test('密码不足 12 位不能提交', () => {
  const errors = validateRegistration({
    username: 'ada',
    email: 'ada@example.com',
    password: 'short-pass',
    confirmPassword: 'short-pass',
  })
  assert.equal(errors.password, '至少 12 个字符')
})

test('确认密码不一致', () => {
  const errors = validateRegistration({
    username: 'ada',
    email: 'ada@example.com',
    password: 'long-enough-password',
    confirmPassword: 'different-password',
  })
  assert.equal(errors.confirmPassword, '两次密码不一致')
})

test('长度分档', () => {
  assert.equal(passwordStrength('short'), 'short')
  assert.equal(passwordStrength('long-enough-pw'), 'ok')
  assert.equal(passwordStrength('sixteen-chars!!'), 'long')
})
```

- [x] **Task 6 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/registerForm.test.ts`
Expected: FAIL

- [x] **Task 6 Step 3: Write minimal implementation**

`validateRegistration` 检查用户名 `/^[A-Za-z0-9_.-]+$/` 且长度 3–64，邮箱含 `@` 和点且长度 3–254，密码长度 12–1024，确认密码相同。`RegisterPage` 使用 `Input.Password`、react-hook-form 和 Ant Design `Form`。有错误时不调用 `http.post('/api/v1/auth/register')`。201 后 `navigate('/login', { state: { registered: true } })`。409 显示「用户名或邮箱不可用」。

- [x] **Task 6 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test && npm run build`
Expected: 测试 PASS；`build` 在本任务结束前可能因路由尚未接入而仍需页面文件可编译。本步先要求 `npm test` PASS，并用 `cd frontend && npx tsc -b --pretty false` 确认新文件没有类型错误。

- [x] **Task 6 Step 5: Commit**

```bash
git add frontend/src/auth/registerForm.ts frontend/src/auth/registerForm.test.ts frontend/src/pages/Auth/RegisterPage.tsx
git commit -m "$(cat <<'EOF'
增加带客户端校验的注册页。

EOF
)"
```

### Task 7: 登录页

对应 `tasks.md` 3.2。

**Files:**
- Create: `frontend/src/pages/Auth/LoginPage.tsx`

**Interfaces:**
- Consumes: `useAuthStore.login`、`sanitizeReturnPath`
- Produces: 默认导出的登录页

- [x] **Task 7 Step 1: 写页面**

页面包含身份、`Input.Password`、记住我和提交按钮。`onFinish` 调用 `login`。提交期间按钮 `loading`。错误是 `ApiClientError` 且 status 为 401 时显示「登录失败」。成功后读取 `location.state.from`，交给 `sanitizeReturnPath`，再 `navigate`。`location.state.registered` 为 true 时显示「可以登录」。表单使用 Ant Design `Form`，回车由 Form 提交。

- [x] **Task 7 Step 2: 类型检查**

Run: `cd frontend && npx tsc -b --pretty false`
Expected: PASS

- [x] **Task 7 Step 3: Commit**

```bash
git add frontend/src/pages/Auth/LoginPage.tsx
git commit -m "$(cat <<'EOF'
增加可回到原页面的登录页。

EOF
)"
```

### Task 8: 公开路由和会话守卫

对应 `tasks.md` 3.3。

**Files:**
- Create: `frontend/src/layouts/AuthLayout.tsx`
- Create: `frontend/src/components/Auth/RequireSession.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes.tsx`

**Interfaces:**
- Consumes: `useAuthStore`、`sanitizeReturnPath`、`useUiStore`
- Produces: `AuthLayout`、`RequireSession`

- [x] **Task 8 Step 1: 写守卫和布局**

`RequireSession` 在 `session` 为空时 `<Navigate to="/login" replace state={{ from: sanitizeReturnPath(pathname + search) }} />`，否则渲染 `<Outlet />`。`AuthLayout` 显示 `readViteEnv().appName`、配色切换，以及登录/注册链接。已登录时两个页面都 `<Navigate to="/" replace />`。

`App.tsx` 改为两条路由树：公开树包含 `/login` 和 `/register`；受保护树用 `RequireSession` 包裹现有 `appPages`。未知路径在受保护树内仍 `<Navigate to="/" replace />`，因此未登录时先到登录页，登录后到仪表盘。

`routes.tsx` 保持六个页面的 lazy import。登录和注册也使用 `lazy`。

- [x] **Task 8 Step 2: 生产构建**

Run: `cd frontend && npm run build`
Expected: PASS，构建输出包含登录和注册的独立 chunk

- [x] **Task 8 Step 3: Commit**

```bash
git add frontend/src/layouts/AuthLayout.tsx frontend/src/components/Auth/RequireSession.tsx frontend/src/App.tsx frontend/src/routes.tsx frontend/src/pages/Auth/LoginPage.tsx frontend/src/pages/Auth/RegisterPage.tsx
git commit -m "$(cat <<'EOF'
未登录时把业务页面转到登录页。

EOF
)"
```

### Task 9: 导航身份和登出

对应 `tasks.md` 4.1。

**Files:**
- Modify: `frontend/src/layouts/AppLayout.tsx`
- Modify: `frontend/src/layouts/AuthLayout.tsx`

**Interfaces:**
- Consumes: `useAuthStore.session`、`useAuthStore.logout`
- Produces: 导航中的用户名或「已登录」、登出按钮

- [x] **Task 9 Step 1: 写导航**

`AppLayout` 在菜单按钮旁显示 `session.username || '已登录'` 和登出按钮。登出调用 `logout()` 后 `navigate('/login', { replace: true })`。窄屏沿用现有菜单按钮，登出按钮和六个链接都放在同一导航里。`AuthLayout` 在窄屏下仍显示登录和注册链接。配色按钮两套布局都保留。

- [x] **Task 9 Step 2: 类型检查和构建**

Run: `cd frontend && npx tsc -b --pretty false && npm run build`
Expected: PASS

- [x] **Task 9 Step 3: Commit**

```bash
git add frontend/src/layouts/AppLayout.tsx frontend/src/layouts/AuthLayout.tsx
git commit -m "$(cat <<'EOF'
在导航中显示当前用户并提供登出。

EOF
)"
```

### Task 10: 整体验证

对应 `tasks.md` 5.1。

**Files:**
- Modify: 无，除非前序命令暴露出类型或格式问题。

- [x] **Task 10 Step 1: 运行全部检查**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: 三个命令都成功。测试输出包含回跳、存储选择和并发刷新。

- [x] **Task 10 Step 2: Commit**

只有 Step 1 修改了文件时才提交。不要把 `openspec/changes/frontend-account-settings/` 加进提交。

```bash
git add frontend
git commit -m "$(cat <<'EOF'
让前端会话测试、检查和构建一起通过。

EOF
)"
```

### Task 11: 登出带上访问令牌

对应 `tasks.md` 6.1。这是验证退回后的修复。规格要求用当前 access token 撤销会话；后端 `POST /api/v1/auth/logout` 依赖该认证头。

**Files:**
- Modify: `frontend/src/auth/http.ts`
- Modify: `frontend/src/auth/http.test.ts`
- Modify: `frontend/src/store/auth.ts`
- Modify: `frontend/src/store/auth.test.ts`
- Modify: `frontend/src/pages/Auth/RegisterPage.tsx`

**Interfaces:**
- Consumes: `createHttpClient`、`useAuthStore`
- Produces: 模块内懒创建、登录登出和注册共用的一个 HTTP 客户端

- [ ] **Task 11 Step 1: Write the failing test**

登出请求带 `Authorization: Bearer`。access token 距过期不足 30 秒时，先刷新一次，再用新 token 发登出。登出返回 401 时只刷新并重试一次。登录、注册、刷新仍然不带 Bearer，也不刷新。状态码大于等于 500 且响应里有英文 `message` 时，错误消息仍是「服务暂时不可用」。

- [ ] **Task 11 Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/auth/http.test.ts`
Expected: FAIL，登出目前不带 Bearer

- [ ] **Task 11 Step 3: Write minimal implementation**

把 `/auth/logout` 移出不刷新、不带 token 的端点。登录、注册、刷新保持原样。状态码大于等于 500 时忽略响应正文，使用「服务暂时不可用」。store 在未注入 client 时复用同一个客户端；注册页使用这个客户端，不再单独创建 `read` 恒为 null 的实例。

- [ ] **Task 11 Step 4: Run test to verify it passes**

Run: `cd frontend && npm test && npx tsc -b --pretty false && npm run build`
Expected: PASS

- [ ] **Task 11 Step 5: Commit**

```bash
git add frontend/src/auth/http.ts frontend/src/auth/http.test.ts frontend/src/store/auth.ts frontend/src/store/auth.test.ts frontend/src/pages/Auth/RegisterPage.tsx
git commit -m "$(cat <<'EOF'
登出时带上访问令牌并撤销服务端会话。

EOF
)"
```
