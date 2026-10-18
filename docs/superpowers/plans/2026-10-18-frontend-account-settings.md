---
change: frontend-account-settings
design-doc: docs/superpowers/specs/2026-10-18-frontend-account-settings-design.md
base-ref: 4654f3c384b17d8ff73d80a581159d2724289e40
archived-with: 2026-10-18-frontend-account-settings
---

# 前端账户设置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让已登录用户从设置页进入个人资料和 API 密钥页，查看并修改资料，管理密钥元数据且不再显示密钥值。

**Architecture:** `/settings` 只放两个链接。两个子路由留在现有 `RequireSession` 内，但不进入顶栏。资料和密钥请求复用会话 axios 实例。分组、校验和载荷放在不依赖 Vite 的纯模块里。

**Tech Stack:** React 18、React Router 7、Ant Design、react-hook-form、Zustand、axios、dayjs、Node 自带测试运行器。

**Spec:** `docs/superpowers/specs/2026-10-18-frontend-account-settings-design.md`

## Global Constraints

- 产物语言：zh-CN。界面错误文案使用设计文档第 6 节的原句。
- 不新增 npm 依赖。
- 不新增 HTTP 客户端，不改登录、刷新和路由守卫的判定。
- 不替换已保存的密钥值，不展示验证次数。
- 不展示密钥明文、掩码、后四位或密文。
- 纯模块不得 import `import.meta` 或 `@/`。
- `VITE_API_BASE_URL` 已经包含 `/api/v1`。axios 的 `url` 使用相对该根的路径，最终地址只出现一次 `/api/v1`。
- 页面不写组件测试。完成标准是类型检查、`npm run lint`、生产构建和 `npm test` 都成功。

---

### Task 1: 设置入口

对应 `tasks.md` 1.1。

**Files:**
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Settings/SettingsPage.tsx`

**Interfaces:**
- Consumes: 现有 `appPages` 与 `RequireSession`
- Produces: `settingsPages`，路径为 `/settings/profile` 和 `/settings/api-keys`。顶栏仍只渲染 `appPages`。

- [x] **Step 1: 增加不进入顶栏的子路由**

把下面的导出加到 `frontend/src/routes.tsx` 的 `appPages` 之后。不要把这两项放进 `appPages`。

```tsx
export const settingsPages: AppPage[] = [
  {
    path: '/settings/profile',
    label: '个人资料',
    Component: lazy(() => import('@/pages/Settings/ProfilePage.tsx')),
  },
  {
    path: '/settings/api-keys',
    label: 'API 密钥',
    Component: lazy(() => import('@/pages/Settings/ApiKeysPage.tsx')),
  },
]
```

`frontend/src/App.tsx` 改为同时引入 `settingsPages`。在 `appPages.map` 之后、`path="*"` 之前加入同样的 `settingsPages.map`。`AppLayout` 继续只映射 `appPages`。

同时创建两个占位页，否则懒加载无法通过类型检查。`frontend/src/pages/Settings/ProfilePage.tsx` 和 `frontend/src/pages/Settings/ApiKeysPage.tsx` 都写成：

```tsx
export default function Page() {
  return <section />
}
```

- [x] **Step 2: 设置页只放两个链接**

用下面的内容替换 `frontend/src/pages/Settings/SettingsPage.tsx`。这个文件不得 import `@/auth/http.ts`、`@/store/auth.ts` 或 `@/account/`。

```tsx
import { Link } from 'react-router-dom'

export default function SettingsPage() {
  return (
    <section>
      <h1>设置</h1>
      <p>
        <Link to="/settings/profile">个人资料</Link>
      </p>
      <p>
        <Link to="/settings/api-keys">API 密钥</Link>
      </p>
    </section>
  )
}
```

- [x] **Step 3: 用类型检查确认设置页通过编译**

运行：

```bash
cd frontend && npx tsc -b --pretty false
```

Expected: 成功退出。占位页会在后续任务被替换。

- [x] **Step 4: Commit**

```bash
git add frontend/src/routes.tsx frontend/src/App.tsx frontend/src/pages/Settings docs/superpowers/specs/2026-10-18-frontend-account-settings-design.md docs/superpowers/plans/2026-10-18-frontend-account-settings.md openspec/changes/frontend-account-settings
git commit -m "$(cat <<'EOF'
设置页改为资料和密钥入口。

EOF
)"
```

### Task 2: 读取个人资料

对应 `tasks.md` 1.2。

- [x] Task 2: 读取个人资料

**Files:**
- Create: `frontend/src/account/profile.ts`
- Create: `frontend/src/account/profile.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/pages/Settings/ProfilePage.tsx`

**Interfaces:**
- Consumes: `GET /users/me` 解开后的对象
- Produces:
  - `readProfile(value: unknown): UserProfile | null`
  - `formatUnixSeconds(seconds: number): string`
  - `UserProfile` 含 `username: string`、`email: string`、`created_at: number`

- [x] **Step 1: Write the failing test**

`frontend/src/account/profile.test.ts`：

```ts
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatUnixSeconds, readProfile } from './profile.ts'

test('无法识别的资料不被当成一份资料', () => {
  assert.equal(readProfile(null), null)
  assert.equal(readProfile({ username: 'ada', email: 'ada@example.com' }), null)
  assert.equal(
    readProfile({ username: 1, email: 'ada@example.com', created_at: 0 }),
    null,
  )
})

test('资料只保留用户名、邮箱和注册时间', () => {
  assert.deepEqual(
    readProfile({
      id: 'user-1',
      username: 'ada',
      email: 'ada@example.com',
      created_at: 0,
      password_hash: 'hidden',
    }),
    { username: 'ada', email: 'ada@example.com', created_at: 0 },
  )
})

test('注册时间格式化为本地日期而不是裸整数', () => {
  const text = formatUnixSeconds(0)
  assert.notEqual(text, '0')
  assert.match(text, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
})
```

把 `frontend/package.json` 的 test 脚本改为：

```json
"test": "node --experimental-strip-types --test src/auth/*.test.ts src/store/*.test.ts src/account/*.test.ts"
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd frontend && node --experimental-strip-types --test src/account/profile.test.ts
```

Expected: FAIL，因为 `./profile.ts` 不存在。

- [x] **Step 3: Write minimal implementation**

`frontend/src/account/profile.ts`：

```ts
import dayjs from 'dayjs'

export interface UserProfile {
  username: string
  email: string
  created_at: number
}

export function readProfile(value: unknown): UserProfile | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (
    typeof record.username !== 'string' ||
    typeof record.email !== 'string' ||
    typeof record.created_at !== 'number'
  ) {
    return null
  }
  return {
    username: record.username,
    email: record.email,
    created_at: record.created_at,
  }
}

export function formatUnixSeconds(seconds: number): string {
  return dayjs.unix(seconds).format('YYYY-MM-DD HH:mm')
}
```

把 `ProfilePage.tsx` 替换为：

```tsx
import { Alert } from 'antd'
import { useEffect, useState } from 'react'
import { formatUnixSeconds, readProfile } from '@/account/profile.ts'
import { useAuthStore } from '@/store/auth.ts'

export default function ProfilePage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [createdAt, setCreatedAt] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const profile = readProfile(
          await useAuthStore.getState().httpClient().get('/users/me'),
        )
        if (!active) return
        if (!profile) {
          setError('服务暂时不可用')
          return
        }
        setUsername(profile.username)
        setEmail(profile.email)
        setCreatedAt(profile.created_at)
      } catch {
        if (!active) return
        setError('服务暂时不可用')
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  if (loading) return <p>加载中</p>
  if (error || createdAt === null) {
    return (
      <section>
        <h1>个人资料</h1>
        <Alert type="error" message={error || '服务暂时不可用'} showIcon />
      </section>
    )
  }

  return (
    <section>
      <h1>个人资料</h1>
      <p>用户名：{username}</p>
      <p>邮箱：{email}</p>
      <p>注册时间：{formatUnixSeconds(createdAt)}</p>
    </section>
  )
}
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd frontend && node --experimental-strip-types --test src/account/profile.test.ts && npx tsc -b --pretty false
```

Expected: 测试通过，类型检查成功退出。

- [x] **Step 5: Commit**

```bash
git add frontend/src/account/profile.ts frontend/src/account/profile.test.ts frontend/package.json frontend/src/pages/Settings/ProfilePage.tsx
git commit -m "$(cat <<'EOF'
资料页读取当前用户并显示本地注册时间。

EOF
)"
```

### Task 3: 修改用户名和邮箱

对应 `tasks.md` 1.3。

- [x] Task 3: 修改用户名和邮箱

**Files:**
- Modify: `frontend/src/auth/registerForm.ts`
- Modify: `frontend/src/account/profile.ts`
- Modify: `frontend/src/account/profile.test.ts`
- Modify: `frontend/src/store/auth.ts`
- Modify: `frontend/src/store/auth.test.ts`
- Modify: `frontend/src/pages/Settings/ProfilePage.tsx`

**Interfaces:**
- Consumes: `validateUsername(username: string): string | undefined` 和 `validateEmail(email: string): string | undefined`
- Produces:
  - `validateProfile(input: ProfileInput): Record<string, string>`
  - `updateUsername(username: string, deps?: AuthDeps): void`
  - `AuthClient.patch(url: string, data?: unknown): Promise<unknown>`
  - `AuthClient.delete(url: string): Promise<unknown>`

- [x] **Step 1: Write the failing test**

在 `profile.test.ts` 追加：

```ts
import { validateProfile } from './profile.ts'

test('含空格的用户名不合法', () => {
  const errors = validateProfile({
    username: 'ada lovelace',
    email: 'ada@example.com',
  })
  assert.equal(
    errors.username,
    '用户名需为 3–64 个字母、数字、下划线、点或连字符',
  )
  assert.equal(errors.email, undefined)
})
```

在 `auth.test.ts` 追加一个测试：先 `writeSession(true, saved, box)` 并 `hydrate`，调用 `updateUsername('grace')` 后，`store.getState().session?.username` 和 `readSession(box)?.username` 都是 `grace`。

- [x] **Step 2: Run test to verify it fails**

```bash
cd frontend && node --experimental-strip-types --test src/account/profile.test.ts src/store/auth.test.ts
```

Expected: FAIL，`validateProfile` 和 `updateUsername` 尚不存在。

- [x] **Step 3: Write minimal implementation**

在 `registerForm.ts` 抽出：

```ts
export function validateUsername(username: string): string | undefined {
  if (
    username.length < 3 ||
    username.length > 64 ||
    !usernamePattern.test(username)
  ) {
    return '用户名需为 3–64 个字母、数字、下划线、点或连字符'
  }
  return undefined
}

export function validateEmail(email: string): string | undefined {
  if (
    email.length < 3 ||
    email.length > 254 ||
    !email.includes('@') ||
    !email.includes('.')
  ) {
    return '请输入有效邮箱'
  }
  return undefined
}
```

`validateRegistration` 改为调用这两个函数，密码和确认密码逻辑不变。

`profile.ts` 追加：

```ts
import { validateEmail, validateUsername } from '../auth/registerForm.ts'

export interface ProfileInput {
  username: string
  email: string
}

export function validateProfile(input: ProfileInput): Record<string, string> {
  const errors: Record<string, string> = {}
  const username = validateUsername(input.username)
  const email = validateEmail(input.email)
  if (username) errors.username = username
  if (email) errors.email = email
  return errors
}
```

`AuthClient` 增加：

```ts
patch(url: string, data?: unknown): Promise<unknown>
delete(url: string): Promise<unknown>
```

在 `createAuthStore` 返回的对象上增加：

```ts
updateUsername(username, deps) {
  const box = storagesFrom(deps)
  const current = readSession(box)
  if (!current) return
  const next = { ...current, username }
  writeSession(remember, next, box)
  set({ session: next })
},
```

把 `ProfilePage.tsx` 替换为带表单的版本。校验失败时不调用 `patch`。409 只设置错误文案，不重置表单。成功后用响应里的用户名和邮箱 `reset`，显示「已保存」；用户名与提交前会话不同才调用 `updateUsername`。

```tsx
import { Alert, Button, Form, Input } from 'antd'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import {
  formatUnixSeconds,
  readProfile,
  validateProfile,
  type ProfileInput,
} from '@/account/profile.ts'
import { ApiClientError } from '@/auth/http.ts'
import { useAuthStore } from '@/store/auth.ts'

function failureText(error: unknown): string {
  if (!(error instanceof ApiClientError)) return '服务暂时不可用'
  if (error.status === 409) return '用户名或邮箱不可用'
  if (error.status === 400) return '请求无效'
  if (error.status === 429) return '请求过于频繁，请稍后再试'
  return '服务暂时不可用'
}

export default function ProfilePage() {
  const updateUsername = useAuthStore((state) => state.updateUsername)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [formMessage, setFormMessage] = useState('')
  const [saved, setSaved] = useState(false)
  const [createdAt, setCreatedAt] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const {
    control,
    handleSubmit,
    setError,
    clearErrors,
    reset,
    formState: { errors },
  } = useForm<ProfileInput>({
    defaultValues: { username: '', email: '' },
  })

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const profile = readProfile(
          await useAuthStore.getState().httpClient().get('/users/me'),
        )
        if (!active) return
        if (!profile) {
          setLoadError('服务暂时不可用')
          return
        }
        reset({ username: profile.username, email: profile.email })
        setCreatedAt(profile.created_at)
      } catch (error) {
        if (!active) return
        setLoadError(failureText(error))
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [reset])

  async function onSubmit(values: ProfileInput) {
    clearErrors()
    setFormMessage('')
    setSaved(false)
    const clientErrors = validateProfile(values)
    for (const name of ['username', 'email'] as const) {
      const message = clientErrors[name]
      if (message) setError(name, { type: 'validate', message })
    }
    if (Object.keys(clientErrors).length > 0) return

    setSubmitting(true)
    const previous = useAuthStore.getState().session?.username
    try {
      const profile = readProfile(
        await useAuthStore.getState().httpClient().patch('/users/me', {
          username: values.username,
          email: values.email,
        }),
      )
      if (!profile) {
        setFormMessage('服务暂时不可用')
        return
      }
      reset({ username: profile.username, email: profile.email })
      setCreatedAt(profile.created_at)
      if (profile.username !== previous) updateUsername(profile.username)
      setSaved(true)
    } catch (error) {
      setFormMessage(failureText(error))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <p>加载中</p>
  if (loadError || createdAt === null) {
    return (
      <section>
        <h1>个人资料</h1>
        <Alert type="error" message={loadError || '服务暂时不可用'} showIcon />
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-md">
      <h1 className="mb-4 text-xl font-semibold">个人资料</h1>
      {saved ? (
        <Alert className="mb-4" type="success" message="已保存" showIcon />
      ) : null}
      {formMessage ? (
        <Alert className="mb-4" type="error" message={formMessage} showIcon />
      ) : null}
      <p className="mb-4">注册时间：{formatUnixSeconds(createdAt)}</p>
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handleSubmit(onSubmit)()
        }}
      >
        <Form.Item
          label="用户名"
          validateStatus={errors.username ? 'error' : undefined}
          help={errors.username?.message}
        >
          <Controller
            name="username"
            control={control}
            render={({ field }) => <Input {...field} />}
          />
        </Form.Item>
        <Form.Item
          label="邮箱"
          validateStatus={errors.email ? 'error' : undefined}
          help={errors.email?.message}
        >
          <Controller
            name="email"
            control={control}
            render={({ field }) => <Input type="email" {...field} />}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          保存
        </Button>
      </Form>
    </section>
  )
}
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd frontend && node --experimental-strip-types --test src/account/profile.test.ts src/auth/registerForm.test.ts src/store/auth.test.ts && npx tsc -b --pretty false
```

Expected: 全部通过。

- [x] **Step 5: Commit**

```bash
git add frontend/src/auth/registerForm.ts frontend/src/account/profile.ts frontend/src/account/profile.test.ts frontend/src/store/auth.ts frontend/src/store/auth.test.ts frontend/src/pages/Settings/ProfilePage.tsx
git commit -m "$(cat <<'EOF'
资料页按注册规则修改用户名和邮箱。

EOF
)"
```

### Task 4: 密钥分组

对应 `tasks.md` 2.1。

- [x] Task 4: 密钥分组

**Files:**
- Create: `frontend/src/account/apiKeys.ts`
- Create: `frontend/src/account/apiKeys.test.ts`

**Interfaces:**
- Consumes: 无
- Produces:
  - `ApiKeyRecord`
  - `readApiKeys(value: unknown): ApiKeyRecord[] | null`
  - `groupApiKeys(keys: readonly ApiKeyRecord[]): ApiKeyGroup[]`
  - `lastUsedLabel(lastUsedAt: number | null): string | null`

- [x] **Step 1: Write the failing test**

```ts
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  groupApiKeys,
  lastUsedLabel,
  readApiKeys,
  type ApiKeyRecord,
} from './apiKeys.ts'

function key(overrides: Partial<ApiKeyRecord>): ApiKeyRecord {
  return {
    id: 'k1',
    provider: 'openai',
    key_name: 'primary',
    created_at: 0,
    last_used_at: null,
    usage_count: 0,
    verified: false,
    ...overrides,
  }
}

test('两个提供商分到对应组，空组不出现', () => {
  const groups = groupApiKeys([
    key({ id: 'o', provider: 'openai' }),
    key({ id: 'a', provider: 'anthropic', key_name: 'claude' }),
  ])
  assert.deepEqual(
    groups.map((group) => group.provider),
    ['openai', 'anthropic'],
  )
  assert.equal(
    groups.some((group) => group.provider === 'siliconflow'),
    false,
  )
})

test('没有最后使用时间时表示尚未使用且次数为 0', () => {
  const [group] = groupApiKeys([key({ usage_count: 0, last_used_at: null })])
  const item = group?.keys[0]
  assert.ok(item)
  assert.equal(item.usage_count, 0)
  assert.equal(lastUsedLabel(item.last_used_at), '尚未使用')
  assert.equal(lastUsedLabel(1), null)
})

test('解析结果不保留密钥字段', () => {
  const parsed = readApiKeys([
    {
      id: 'k1',
      provider: 'openai',
      key_name: 'primary',
      created_at: 1,
      last_used_at: null,
      usage_count: 0,
      verified: false,
      api_key: 'sk-secret',
    },
  ])
  assert.equal(parsed?.[0] && Object.hasOwn(parsed[0], 'api_key'), false)
  assert.equal(readApiKeys({ data: [] }), null)
})
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts
```

Expected: FAIL，模块不存在。

- [x] **Step 3: Write minimal implementation**

`frontend/src/account/apiKeys.ts`：

```ts
export const providers = ['openai', 'anthropic', 'siliconflow'] as const

export type Provider = (typeof providers)[number]

export interface ApiKeyRecord {
  id: string
  provider: Provider
  key_name: string
  created_at: number
  last_used_at: number | null
  usage_count: number
  verified: boolean
}

export interface ApiKeyGroup {
  provider: Provider
  label: string
  keys: ApiKeyRecord[]
}

const labels: Record<Provider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  siliconflow: 'SiliconFlow',
}

function isProvider(value: unknown): value is Provider {
  return providers.includes(value as Provider)
}

export function readApiKey(value: unknown): ApiKeyRecord | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const lastUsed = record.last_used_at
  if (
    typeof record.id !== 'string' ||
    !isProvider(record.provider) ||
    typeof record.key_name !== 'string' ||
    typeof record.created_at !== 'number' ||
    typeof record.verified !== 'boolean' ||
    (lastUsed !== null && typeof lastUsed !== 'number')
  ) {
    return null
  }
  return {
    id: record.id,
    provider: record.provider,
    key_name: record.key_name,
    created_at: record.created_at,
    last_used_at: lastUsed,
    usage_count: typeof record.usage_count === 'number' ? record.usage_count : 0,
    verified: record.verified,
  }
}

export function readApiKeys(value: unknown): ApiKeyRecord[] | null {
  if (!Array.isArray(value)) return null
  const keys: ApiKeyRecord[] = []
  for (const item of value) {
    const key = readApiKey(item)
    if (key) keys.push(key)
  }
  return keys
}

export function groupApiKeys(keys: readonly ApiKeyRecord[]): ApiKeyGroup[] {
  return providers.flatMap((provider) => {
    const matched = keys.filter((key) => key.provider === provider)
    if (matched.length === 0) return []
    return [{ provider, label: labels[provider], keys: matched }]
  })
}

export function lastUsedLabel(lastUsedAt: number | null): string | null {
  return lastUsedAt === null ? '尚未使用' : null
}
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts
```

Expected: PASS。

- [x] **Step 5: Commit**

```bash
git add frontend/src/account/apiKeys.ts frontend/src/account/apiKeys.test.ts
git commit -m "$(cat <<'EOF'
按提供商分组 API 密钥元数据。

EOF
)"
```

### Task 5: 添加密钥

对应 `tasks.md` 2.2。

- [x] Task 5: 添加密钥

**Files:**
- Modify: `frontend/src/account/apiKeys.ts`
- Modify: `frontend/src/account/apiKeys.test.ts`
- Modify: `frontend/src/pages/Settings/ApiKeysPage.tsx`

**Interfaces:**
- Consumes: `readApiKeys`、`groupApiKeys`、`lastUsedText`、`formatUnixSeconds`
- Produces:
  - `rejectApiKey(value: string): string | null`
  - `validateKeyName(name: string): string | null`

- [x] **Step 1: Write the failing test**

```ts
import { rejectApiKey } from './apiKeys.ts'

test('拒绝空白和环境变量引用', () => {
  for (const value of ['', '   ', 'env:OPENAI_API_KEY', 'ENV:TOKEN', '${KEY}']) {
    assert.equal(rejectApiKey(value), '需要真实密钥值')
  }
  assert.equal(rejectApiKey('sk-live'), null)
})
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts
```

Expected: FAIL，`rejectApiKey` 未导出。

- [x] **Step 3: Write minimal implementation**

```ts
export function rejectApiKey(value: string): string | null {
  if (
    value.trim().length === 0 ||
    value.toLowerCase().startsWith('env:') ||
    value.startsWith('${')
  ) {
    return '需要真实密钥值'
  }
  return null
}

export function validateKeyName(name: string): string | null {
  if (name.length < 1 || name.length > 100) return '名称需为 1–100 个字符'
  return null
}
```

把 `ApiKeysPage.tsx` 写成下面的列表和添加表单。`KeyRow` 的参数类型是 `ApiKeyRecord`，函数体内不得出现 `api_key`。

```tsx
import { Alert, Button, Form, Input, Select } from 'antd'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import {
  groupApiKeys,
  lastUsedLabel,
  providers,
  readApiKeys,
  rejectApiKey,
  validateKeyName,
  type ApiKeyRecord,
  type Provider,
} from '@/account/apiKeys.ts'
import { formatUnixSeconds } from '@/account/profile.ts'
import { useAuthStore } from '@/store/auth.ts'

interface AddInput {
  provider: Provider
  key_name: string
  api_key: string
}

function KeyRow({ item }: { item: ApiKeyRecord }) {
  return (
    <li>
      <p>{item.key_name}</p>
      <p>{item.provider}</p>
      <p>创建时间：{formatUnixSeconds(item.created_at)}</p>
      <p>{item.verified ? '已验证' : '未验证'}</p>
      <p>使用次数：{item.usage_count}</p>
      <p>
        {item.last_used_at === null
          ? lastUsedLabel(null)
          : `最后使用：${formatUnixSeconds(item.last_used_at)}`}
      </p>
    </li>
  )
}

export default function ApiKeysPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [keys, setKeys] = useState<ApiKeyRecord[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const {
    control,
    handleSubmit,
    reset,
    setError: setFieldError,
    formState: { errors },
  } = useForm<AddInput>({
    defaultValues: { provider: 'openai', key_name: '', api_key: '' },
  })

  async function load() {
    const parsed = readApiKeys(
      await useAuthStore.getState().httpClient().get('/api-keys'),
    )
    if (!parsed) {
      setError('服务暂时不可用')
      setKeys([])
      return
    }
    setError('')
    setKeys(parsed)
  }

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        if (active) await load()
      } catch {
        if (active) setError('服务暂时不可用')
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  async function onSubmit(values: AddInput) {
    setFormMessage('')
    const nameError = validateKeyName(values.key_name)
    const keyError = rejectApiKey(values.api_key)
    if (nameError) setFieldError('key_name', { type: 'validate', message: nameError })
    if (keyError) setFieldError('api_key', { type: 'validate', message: keyError })
    if (nameError || keyError) return
    setSubmitting(true)
    try {
      await useAuthStore.getState().httpClient().post('/api-keys', {
        provider: values.provider,
        key_name: values.key_name,
        api_key: values.api_key,
      })
      reset({ provider: 'openai', key_name: '', api_key: '' })
      await load()
    } catch {
      setFormMessage('服务暂时不可用')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <p>加载中</p>
  if (error) {
    return (
      <section>
        <h1>API 密钥</h1>
        <Alert type="error" message={error} showIcon />
      </section>
    )
  }

  const groups = groupApiKeys(keys)
  return (
    <section>
      <h1>API 密钥</h1>
      <p>密钥保存后不再显示</p>
      {formMessage ? <Alert type="error" message={formMessage} showIcon /> : null}
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handleSubmit(onSubmit)()
        }}
      >
        <Form.Item label="提供商">
          <Controller
            name="provider"
            control={control}
            render={({ field }) => (
              <Select
                {...field}
                options={providers.map((provider) => ({
                  value: provider,
                  label: provider,
                }))}
              />
            )}
          />
        </Form.Item>
        <Form.Item
          label="名称"
          validateStatus={errors.key_name ? 'error' : undefined}
          help={errors.key_name?.message}
        >
          <Controller
            name="key_name"
            control={control}
            render={({ field }) => <Input {...field} />}
          />
        </Form.Item>
        <Form.Item
          label="密钥"
          validateStatus={errors.api_key ? 'error' : undefined}
          help={errors.api_key?.message}
        >
          <Controller
            name="api_key"
            control={control}
            render={({ field }) => <Input.Password {...field} />}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          添加
        </Button>
      </Form>
      {groups.length === 0 ? <p>还没有 API 密钥</p> : null}
      {groups.map((group) => (
        <section key={group.provider}>
          <h2>{group.label}</h2>
          <ul>
            {group.keys.map((item) => (
              <KeyRow key={item.id} item={item} />
            ))}
          </ul>
        </section>
      ))}
    </section>
  )
}
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts && npx tsc -b --pretty false
```

Expected: 测试通过，类型检查成功退出。

- [x] **Step 5: Commit**

```bash
git add frontend/src/account/apiKeys.ts frontend/src/account/apiKeys.test.ts frontend/src/pages/Settings/ApiKeysPage.tsx
git commit -m "$(cat <<'EOF'
密钥页用密码框添加密钥并拒绝非法值。

EOF
)"
```

### Task 6: 改名、删除和验证

对应 `tasks.md` 2.3。

- [x] Task 6: 改名、删除和验证

**Files:**
- Modify: `frontend/src/account/apiKeys.ts`
- Modify: `frontend/src/account/apiKeys.test.ts`
- Modify: `frontend/src/pages/Settings/ApiKeysPage.tsx`

**Interfaces:**
- Consumes: `validateKeyName`、`readApiKeys`
- Produces:
  - `renamePayload(keyName: string): { key_name: string }`
  - `verifyStatusText(ok: boolean): '验证成功' | '验证失败'`

- [x] **Step 1: Write the failing test**

```ts
import { renamePayload, verifyStatusText } from './apiKeys.ts'

test('改名载荷只有 key_name', () => {
  const payload = renamePayload('renamed')
  assert.deepEqual(payload, { key_name: 'renamed' })
  assert.equal(Object.hasOwn(payload, 'api_key'), false)
})

test('验证文案只有成功或失败', () => {
  assert.equal(verifyStatusText(true), '验证成功')
  assert.equal(verifyStatusText(false), '验证失败')
})
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts
```

Expected: FAIL，两个函数未导出。

- [x] **Step 3: Write minimal implementation**

```ts
export function renamePayload(keyName: string): { key_name: string } {
  return { key_name: keyName }
}

export function verifyStatusText(ok: boolean): '验证成功' | '验证失败' {
  return ok ? '验证成功' : '验证失败'
}
```

在 `KeyRow` 中增加改名、删除和验证，并把组件内的 `load` 作为 prop 传入。改名只渲染名称输入，不渲染 `Input.Password`。保存前调用 `validateKeyName`，失败则不发请求。通过后调用 `patch('/api-keys/' + item.id, renamePayload(name))`，再执行现有的 `load`。

删除使用：

```tsx
Modal.confirm({
  title: '删除这条密钥？',
  okText: '删除',
  cancelText: '取消',
  onOk: async () => {
    await useAuthStore.getState().httpClient().delete('/api-keys/' + item.id)
    await load()
  },
})
```

取消不进入 `onOk`，因此不发 `delete`。

验证把 `item.id` 放进组件内的加载 id。请求：

```tsx
const result: unknown = await useAuthStore
  .getState()
  .httpClient()
  .post('/api-keys/' + item.id + '/verify')
const ok =
  typeof result === 'object' &&
  result !== null &&
  'ok' in result &&
  result.ok === true
setNotice(verifyStatusText(ok))
await load()
```

`setNotice` 显示在页面顶部。不要读取 `message`。捕获到 `ApiClientError` 且 status 为 429 时显示「请求过于频繁，请稍后再试」；其他失败显示「服务暂时不可用」。请求结束后从加载集合移除该 id。

- [x] **Step 4: Run test to verify it passes**

```bash
cd frontend && node --experimental-strip-types --test src/account/apiKeys.test.ts && npx tsc -b --pretty false
```

Expected: 测试通过，类型检查成功退出。

- [x] **Step 5: Commit**

```bash
git add frontend/src/account/apiKeys.ts frontend/src/account/apiKeys.test.ts frontend/src/pages/Settings/ApiKeysPage.tsx
git commit -m "$(cat <<'EOF'
密钥页只提交新名称，并在确认后删除或验证。

EOF
)"
```

### Task 7: 整体验证

对应 `tasks.md` 3.1。

- [x] Task 7: 整体验证

**Files:**
- Modify: `openspec/changes/frontend-account-settings/tasks.md`（仅把 1.1 到 3.1 勾选为完成，不改任务正文）

- [x] **Step 1: 运行前端检查**

```bash
cd frontend && npx tsc -b --pretty false && npm run lint && npm test && npm run build
```

Expected: 四条命令都成功退出。

- [x] **Step 2: 勾选任务并提交**

确认 `tasks.md` 七个复选框都是 `[x]`。不要勾选本计划文件里的步骤来代替 `tasks.md`。

```bash
git add openspec/changes/frontend-account-settings/tasks.md
git commit -m "$(cat <<'EOF'
记录账户设置任务已完成。

EOF
)"
```
