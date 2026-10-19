import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

// Compile the real TSX components with the app's existing Vite configuration.
const server = await createServer({
  server: { middlewareMode: true, watch: null, hmr: false },
  appType: 'custom',
})
after(() => server.close())
const { RequireRole } = await server.ssrLoadModule(
  '/src/components/Auth/RequireRole.tsx',
)
const { RoleContext } = await server.ssrLoadModule('/src/auth/roleContext.ts')
const { default: SettingsPage } = await server.ssrLoadModule(
  '/src/pages/Settings/SettingsPage.tsx',
)

function render(
  state: { status: string; role: string | null },
  child: ReturnType<typeof createElement>,
) {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      {},
      createElement(
        RoleContext.Provider,
        { value: { state, reload() {} } },
        child,
      ),
    ),
  )
}

test('真实守卫仅为管理员渲染受限内容', () => {
  const page = createElement(
    RequireRole,
    { allowedRoles: ['admin'] },
    'private-system-data',
  )
  const user = render({ status: 'ready', role: 'user' }, page)
  assert.match(user, /无权访问此页面/)
  assert.doesNotMatch(user, /private-system-data/)
  assert.match(user, /href="\/settings"/)
  assert.match(
    render({ status: 'ready', role: 'admin' }, page),
    /private-system-data/,
  )
})

test('真实守卫在加载和失败时不渲染受限内容', () => {
  const page = createElement(
    RequireRole,
    { allowedRoles: ['admin'] },
    'private-system-data',
  )
  const loading = render({ status: 'loading', role: null }, page)
  assert.match(loading, /正在确认访问权限/)
  assert.doesNotMatch(loading, /private-system-data/)
  const error = render({ status: 'error', role: null }, page)
  assert.match(error, /无法确认访问权限/)
  assert.match(error, /重试/)
  assert.doesNotMatch(error, /private-system-data/)
})

test('角色查询失败不阻塞普通页面', () => {
  assert.match(
    render(
      { status: 'error', role: null },
      createElement(RequireRole, {}, '普通页面'),
    ),
    /普通页面/,
  )
})

test('设置页按真实路由配置过滤管理员入口', () => {
  const page = createElement(SettingsPage)
  const user = render({ status: 'ready', role: 'user' }, page)
  assert.match(user, /个人资料/)
  assert.match(user, /API 密钥/)
  assert.doesNotMatch(user, /系统状态/)
  assert.doesNotMatch(render({ status: 'error', role: null }, page), /系统状态/)
  assert.match(
    render({ status: 'ready', role: 'admin' }, page),
    /href="\/settings\/system"/,
  )
})
