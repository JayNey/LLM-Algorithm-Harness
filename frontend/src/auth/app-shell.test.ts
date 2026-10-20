import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { createServer } from 'vite'
const server = await createServer({
  server: { middlewareMode: true, watch: null, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true, include: [] },
  appType: 'custom',
})
after(() => server.close())
const { AppLayout } = await server.ssrLoadModule('/src/layouts/AppLayout.tsx')
const { RoleContext } = await server.ssrLoadModule('/src/auth/roleContext.ts')
const { useUiStore } = await server.ssrLoadModule('/src/store/ui.ts')
function render(role: string | null) {
  return renderToStaticMarkup(
    createElement(
      StaticRouter,
      { location: '/settings/profile' },
      createElement(
        RoleContext.Provider,
        {
          value: {
            state: { status: role ? 'ready' : 'loading', role },
            reload() {},
          },
        },
        createElement(AppLayout),
      ),
    ),
  )
}
test('真实外壳提供Frontier、共享分组导航、面包屑和风格控制', () => {
  const html = render('user')
  assert.match(html, /harness-frontier.svg/)
  assert.match(html, /基准测试/)
  assert.match(html, /帮助文档/)
  assert.match(html, /选择页面风格/)
  assert.match(html, /面包屑/)
  assert.match(html, /常用页面/)
  assert.doesNotMatch(html, /href="\/settings\/system"/)
  assert.match(render('admin'), /href="\/settings\/system"/)
  assert.doesNotMatch(render(null), /href="\/settings\/system"/)
})
test('三套风格共享同一个业务外壳与可访问主内容', () => {
  for (const variant of ['orbit', 'precision', 'studio']) {
    useUiStore.getState().setAppearanceVariant(variant)
    const html = render('user')
    assert.match(html, /跳至主内容/)
    assert.match(html, /id="main"/)
    assert.match(html, /通知中心/)
  }
})
