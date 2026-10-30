/* global localStorage, document, window, PopStateEvent, innerWidth */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || 'playwright',
)
const base = process.env.EVALUATION_BASE_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  reducedMotion: 'reduce',
})
const page = await context.newPage()
page.setDefaultTimeout(8000)
const errors = []
const calls = []
page.on('pageerror', (e) => errors.push(e.message))
let row = {
  evaluation_id: 'eval-one',
  created_at: '2026-10-30T00:00:00Z',
  updated_at: '2026-10-30T00:00:00Z',
  status: 'running',
  can_start: false,
  can_cancel: true,
  async_task_id: 'async-one',
  can_pause: true,
  can_resume: false,
  can_update: false,
  can_delete: false,
  execution_progress: { completed_units: 1, total_units: 2, percentage: 50 },
  strategy_names: ['direct'],
  model: 'model',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: 5,
  error_message: null,
  progress: null,
}
let failure = 0
let reads = 0
let hold
let release
let mutateStarted
let started
await context.addInitScript(() =>
  localStorage.setItem(
    'llm-harness-session',
    JSON.stringify({
      marker: 'management-owner',
      username: 'fixture',
      expiresAt: Date.now() + 3600000,
    }),
  ),
)
await context.route('**/api/v1/**', async (route) => {
  const request = route.request()
  const path = new URL(request.url()).pathname.replace('/api/v1', '')
  const method = request.method()
  calls.push({ path, method })
  const headers = {
    'access-control-allow-origin': base,
    'access-control-allow-credentials': 'true',
    'access-control-allow-methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers': 'content-type,x-csrf-token',
  }
  const send = (data, status = 200) =>
    route.fulfill({ status, headers, json: { data } })
  if (method === 'OPTIONS') return route.fulfill({ status: 204, headers })
  if (path === '/users/me') return send({ username: 'fixture', role: 'user' })
  if (path === '/auth/refresh')
    return route.fulfill({ status: 401, headers, json: { message: 'expired' } })
  if (method === 'GET' && path.startsWith('/evaluations/')) {
    reads++
    return send({ ...row, evaluation_id: path.split('/').at(-1) })
  }
  if (method === 'GET' && path === '/evaluations')
    return send({ items: [], total: 0, limit: 20, offset: 0, has_more: false })
  if (method !== 'GET') {
    mutateStarted?.()
    if (hold) await hold
    if (failure === -1) return route.abort('timedout')
    if (failure)
      return route.fulfill({
        status: failure,
        headers,
        json: { message: 'operation rejected' },
      })
    if (
      path === '/tasks/async-one/pause' ||
      path === '/tasks/async-latest/pause'
    )
      row = { ...row, status: 'paused', can_pause: false, can_resume: true }
    else if (path === '/tasks/async-one/resume')
      row = {
        ...row,
        status: 'running',
        can_pause: true,
        can_resume: false,
        async_task_id: 'async-latest',
      }
    else if (method === 'PATCH')
      row = { ...row, budget_cap_usd: request.postDataJSON().budget_cap_usd }
    else if (method === 'DELETE') return route.fulfill({ status: 204, headers })
    else throw new Error('unexpected mutation ' + method + ' ' + path)
    return send(row)
  }
  return send({})
})
await context.routeWebSocket(/\/ws/, (ws) => ws.onMessage(() => {}))
try {
  await page.goto(base + '/evaluations/eval-one')
  await page.getByRole('button', { name: '暂停任务', exact: true }).click()
  await page.getByRole('button', { name: '恢复任务', exact: true }).waitFor()
  assert.ok(calls.some((c) => c.path === '/tasks/async-one/pause'))
  await page.getByRole('button', { name: '恢复任务', exact: true }).click()
  await page.getByRole('button', { name: '暂停任务', exact: true }).waitFor()
  await page.reload()
  assert.equal(
    await page.getByRole('button', { name: '保存预算', exact: true }).count(),
    0,
  )
  await page.getByRole('button', { name: '暂停任务', exact: true }).click()
  await page.getByRole('button', { name: '恢复任务', exact: true }).waitFor()
  assert.ok(calls.some((c) => c.path === '/tasks/async-latest/pause'))
  // Missing association must fail closed even if a stale capability says true.
  row = { ...row, async_task_id: null }
  await page.reload()
  assert.equal(
    await page.getByRole('button', { name: '暂停任务', exact: true }).count(),
    0,
  )
  row = {
    ...row,
    status: 'pending',
    can_pause: false,
    can_cancel: false,
    can_update: true,
    can_delete: true,
  }
  await page.reload()
  await page.getByLabel('预算上限（USD）', { exact: true }).fill('12.5')
  await page.getByRole('button', { name: '保存预算', exact: true }).click()
  await page
    .getByText('操作已完成，已读取最新状态。', { exact: true })
    .waitFor()
  assert.equal(row.budget_cap_usd, 12.5)
  for (const code of [-1, 400, 403, 404, 409, 500]) {
    failure = code
    const before = reads
    await page.getByLabel('预算上限（USD）', { exact: true }).fill('20')
    await page.getByRole('button', { name: '保存预算', exact: true }).click()
    await page.getByText('操作尚未确认', { exact: true }).waitFor()
    await page.waitForFunction(
      () => !document.querySelector('[aria-busy="true"]'),
    )
    assert.ok(reads > before, 'failure must reconcile')
    assert.equal(row.budget_cap_usd, 12.5)
  }
  failure = 0
  // Reserve synchronously so two clicks cannot submit two PATCH requests.
  hold = new Promise((resolve) => {
    release = resolve
  })
  started = new Promise((resolve) => {
    mutateStarted = resolve
  })
  const patches = calls.filter((c) => c.method === 'PATCH').length
  await page.getByLabel('预算上限（USD）', { exact: true }).fill('25')
  await page
    .getByRole('button', { name: '保存预算', exact: true })
    .evaluate((button) => {
      button.click()
      button.click()
    })
  await started
  assert.equal(calls.filter((c) => c.method === 'PATCH').length, patches + 1)
  release()
  hold = null
  mutateStarted = null
  await page
    .getByText('操作已完成，已读取最新状态。', { exact: true })
    .waitFor()
  // Inspect Chinese mobile and English desktop without replacing real components.
  await page.setViewportSize({ width: 320, height: 844 })
  await page.screenshot({ path: '/tmp/issue320-mobile.png', fullPage: true })
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  )
  await page.evaluate(() =>
    localStorage.setItem('llm-harness-language', 'en-US'),
  )
  await page.reload()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'Save budget', exact: true }).waitFor()
  await page.screenshot({ path: '/tmp/issue320-desktop.png', fullPage: true })
  await page.evaluate(() =>
    localStorage.setItem('llm-harness-language', 'zh-CN'),
  )
  await page.reload()
  await page.getByRole('button', { name: '删除评估', exact: true }).click()
  await page.getByRole('dialog').waitFor()
  await page.keyboard.press('Escape')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 0)
  await page.getByRole('button', { name: '删除评估', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await page.waitForURL(/\/evaluations(?:\?|$)/)
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 1)
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  )
  // An old operation cannot navigate a different evaluation when it completes.
  row = { ...row, status: 'pending' }
  hold = new Promise((resolve) => {
    release = resolve
  })
  await page.goto(base + '/evaluations/eval-one')
  await page.getByRole('button', { name: '删除评估', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await page.evaluate(() => {
    window.history.pushState({}, '', '/evaluations/eval-two')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  release()
  hold = null
  await page.waitForURL(/\/evaluations\/eval-two$/)
  await page
    .getByRole('heading', { name: '评估任务详情', exact: true })
    .waitFor()
  // Replacing the session remounts the action scope. Old permission failures
  // must not clear or overwrite the new session, even on the same evaluation.
  hold = new Promise((resolve) => {
    release = resolve
  })
  started = new Promise((resolve) => {
    mutateStarted = resolve
  })
  await page.getByLabel('预算上限（USD）', { exact: true }).fill('30')
  await page.getByRole('button', { name: '保存预算', exact: true }).click()
  await started
  await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/store/auth.ts')
    useAuthStore.setState({
      session: {
        marker: 'new-owner',
        username: 'new-owner',
        expiresAt: Date.now() + 3600000,
      },
    })
  })
  failure = 403
  release()
  hold = null
  mutateStarted = null
  await page.getByLabel('预算上限（USD）', { exact: true }).waitFor()
  assert.equal(await page.getByText('操作尚未确认', { exact: true }).count(), 0)
  failure = 401
  await page.getByLabel('预算上限（USD）', { exact: true }).fill('40')
  await page.getByRole('button', { name: '保存预算', exact: true }).click()
  await page.waitForURL(/\/login/)
  assert.deepEqual(errors, [])
  console.log(
    JSON.stringify(
      {
        passed: true,
        checks: [
          'pause/resume actual task ID',
          'reload',
          'missing link',
          'budget PATCH',
          'timeout/400/403/404/409/500 reconcile',
          'keyboard confirmation',
          'delete 204 navigation',
          'mobile overflow',
          'unmounted mutation',
          'latest task ID',
          'synchronous double-click guard',
          'Chinese mobile / English desktop',
          'session replacement',
          '401 login recovery',
        ],
        mutations: calls.filter((c) =>
          ['POST', 'PATCH', 'DELETE'].includes(c.method),
        ),
      },
      null,
      2,
    ),
  )
} finally {
  await browser.close()
}
