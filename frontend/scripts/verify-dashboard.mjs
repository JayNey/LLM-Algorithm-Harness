/* global localStorage, window, document, URL, console */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.DASHBOARD_BASE_URL || 'http://127.0.0.1:5192'
const output = resolve(process.env.DASHBOARD_QA_DIR || '/tmp/dashboard-qa')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
})
const report = {
  layer: 'Chromium with HTTP fixtures; no live backend or provider calls',
  checks: [],
  requests: [],
  errors: [],
  screenshots: [],
}
const task = (id) => ({
  evaluation_id: `real-task-${id}-long-identifier`,
  created_at: `2026-10-${String(id + 1).padStart(2, '0')}T01:00:00Z`,
  updated_at: '2026-10-27T01:00:00Z',
  status: id === 22 ? 'running' : 'completed',
  can_start: false,
  can_cancel: id === 22,
  execution_progress: { completed_units: 2, total_units: 8, percentage: 25 },
  strategy_names: ['direct'],
  model: 'real-model-with-long-model-name-32B',
  problem_count: 8,
  spent_usd: 0.000068,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
})
const system = {
  uptime_seconds: 3600,
  task_count: 23,
  task_counts: { running: 12 },
  async_task_count: null,
  async_task_counts: null,
  health: {
    status: 'degraded',
    checks: {
      database: { status: 'ok' },
      redis: { status: 'unavailable' },
      workers: { status: 'unknown' },
      sandbox: { status: 'not_checked' },
    },
  },
  resources: {
    cpu: { status: 'unknown', percent: null, sample_seconds: 0.1 },
    memory: {
      status: 'unknown',
      total_bytes: null,
      available_bytes: null,
      used_bytes: null,
      percent: null,
    },
    disk: {
      status: 'unknown',
      total_bytes: null,
      used_bytes: null,
      free_bytes: null,
      percent: null,
    },
  },
  workers: { status: 'unknown' },
  queue_metrics: {
    broker_queue: { status: 'unknown', waiting: null, queues: null },
    database_pending: { status: 'unknown', count: null },
    worker_reserved: { status: 'unknown', count: null },
  },
}
async function setup({
  variant = 'orbit',
  theme = 'dark',
  width = 1440,
  role = 'user',
} = {}) {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
  })
  const state = {
    role,
    total: 23,
    costFailure: false,
    listFailure: false,
    roleFailure: false,
    gate: null,
  }
  await context.addInitScript(
    ({ variant, theme }) => {
      localStorage.setItem(
        'llm-harness-session',
        JSON.stringify({
          marker: 'dashboard-fixture',
          username: 'qa',
          expiresAt: Date.now() + 3600000,
        }),
      )
      localStorage.setItem(
        'llm-harness-ui',
        JSON.stringify({
          appearanceVariant: variant,
          themes: { orbit: theme, precision: theme, studio: theme },
        }),
      )
    },
    { variant, theme },
  )
  const calls = []
  await context.route('**/api/v1/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace('/api/v1', '')
    calls.push({ path, method: request.method(), query: url.search })
    const headers = {
      'access-control-allow-origin': base,
      'access-control-allow-credentials': 'true',
    }
    const send = (data, status = 200) =>
      route.fulfill({
        status,
        headers,
        json: {
          success: status === 200,
          data,
          message: status === 200 ? 'OK' : 'Fixture unavailable',
        },
      })
    if (request.method() === 'OPTIONS')
      return route.fulfill({
        status: 204,
        headers: {
          ...headers,
          'access-control-allow-methods': 'GET',
          'access-control-allow-headers': 'content-type',
        },
      })
    assert.equal(request.method(), 'GET', 'dashboard must remain read-only')
    if (path === '/users/me')
      return send(
        { username: 'qa', role: state.role },
        state.roleFailure ? 500 : 200,
      )
    if (path === '/evaluations') {
      const gate = state.gate
      const observedTotal = state.total
      if (gate) await gate
      if (state.listFailure) return send(null, 500)
      const limit = Number(url.searchParams.get('limit')),
        offset = Number(url.searchParams.get('offset'))
      const status = url.searchParams.get('status')
      const total =
        observedTotal === 0
          ? 0
          : status === 'running'
            ? 12
            : status === 'completed'
              ? 9
              : observedTotal
      return send({
        items: Array.from(
          { length: Math.min(limit, Math.max(total - offset, 0)) },
          (_, i) => task(offset + i),
        ),
        total,
        limit,
        offset,
        has_more: offset + limit < total,
      })
    }
    if (path === '/costs/summary')
      return send(
        { total_cost_usd: state.total ? 17.123456 : 0 },
        state.costFailure ? 500 : 200,
      )
    if (path === '/system/status') return send(system)
    if (path.startsWith('/evaluations/')) return send(task(22))
    throw new Error(`Unexpected request ${path}`)
  })
  const page = await context.newPage()
  page.on('pageerror', (error) => report.errors.push(error.message))
  return { context, page, state, calls }
}
async function ready(page) {
  await page.getByRole('table', { name: '最近评估', exact: true }).waitFor()
  await page
    .locator('.metric-strip')
    .getByText('$17.123456', { exact: false })
    .waitFor()
}
try {
  for (const variant of ['orbit', 'precision', 'studio'])
    for (const theme of ['light', 'dark'])
      for (const width of [320, 768, 1024, 1440]) {
        const { context, page, calls } = await setup({ variant, theme, width })
        await page.goto(base)
        await ready(page)
        assert.match(
          await page.locator('.metric-strip').textContent(),
          /评估与已完成基准/,
        )
        assert.match(
          await page.locator('.insights').textContent(),
          /未包含实验与 A\/B/,
        )
        const numbers = await page
          .locator('.metric-strip strong')
          .allTextContents()
        assert.deepEqual(numbers, [
          '23个任务',
          '12个任务',
          '9个任务',
          '$17.123456USD',
        ])
        const ids = await page
          .locator('tbody tr td:first-child a')
          .allTextContents()
        assert.deepEqual(
          ids,
          [22, 21, 20, 19, 18].map((id) => `real-task-${id}-long-identifier`),
        )
        assert.equal(
          calls.filter((call) => call.path === '/system/status').length,
          0,
        )
        assert.equal(await page.getByLabel('预览数据状态').count(), 0)
        assert.equal(
          await page
            .locator('.dashboard-page')
            .getByText(/Mock|Qwen 基线领先|整体 Pass@1/)
            .count(),
          0,
        )
        const sizes = await page.evaluate(() => ({
          width: window.innerWidth,
          scroll: document.documentElement.scrollWidth,
        }))
        assert.ok(
          sizes.scroll <= sizes.width,
          `Overflow ${variant}/${theme}/${width}: ${JSON.stringify(sizes)}`,
        )
        if (width === 320 || width === 1440) {
          const path = `${variant}-${theme}-${width}.png`
          await page.screenshot({ path: resolve(output, path), fullPage: true })
          report.screenshots.push(path)
        }
        report.checks.push(`matrix ${variant}/${theme}/${width}`)
        report.requests.push(...calls)
        await context.close()
      }
  {
    const { context, page, state, calls } = await setup({ role: 'admin' })
    await page.goto(base)
    await ready(page)
    await page.getByText('降级', { exact: true }).waitFor()
    await page.getByText('不可用', { exact: true }).waitFor()
    await page.getByText('未知', { exact: true }).waitFor()
    assert.equal(
      calls.filter((call) => call.path === '/system/status').length,
      1,
    )
    await page.screenshot({
      path: resolve(output, 'admin-health.png'),
      fullPage: true,
    })
    report.screenshots.push('admin-health.png')

    state.costFailure = true
    await page.getByRole('button', { name: '刷新数据', exact: true }).click()
    await page.getByRole('button', { name: '重试累计调用费用' }).waitFor()
    assert.equal(
      await page.getByRole('table', { name: '最近评估', exact: true }).count(),
      1,
    )
    assert.equal(
      await page.locator('.metric-strip strong').last().textContent(),
      '—',
    )
    state.costFailure = false
    await page.getByRole('button', { name: '重试累计调用费用' }).click()
    await ready(page)
    state.listFailure = true
    await page.getByRole('button', { name: '刷新数据', exact: true }).click()
    await page.getByRole('button', { name: '重试评估总数' }).waitFor()
    assert.equal(
      await page.locator('.metric-strip strong').last().textContent(),
      '$17.123456USD',
    )
    state.listFailure = false
    await page.getByRole('button', { name: '刷新数据', exact: true }).click()
    await ready(page)
    await page.locator('tbody tr td:first-child a').first().click()
    await page.waitForURL('**/evaluations/real-task-22-long-identifier')
    report.checks.push(
      'admin degraded/unknown health; cost and list failure isolation; retry; real detail route',
    )
    await context.close()
  }
  {
    const { context, page, state } = await setup()
    state.total = 0
    await page.goto(base)
    await page.getByText('还没有评估任务', { exact: true }).waitFor()
    assert.deepEqual(
      await page.locator('.metric-strip strong').allTextContents(),
      ['0个任务', '0个任务', '0个任务', '$0USD'],
    )
    await page.getByRole('link', { name: '创建第一次评估' }).click()
    await page.waitForURL('**/evaluations/new')
    report.checks.push('empty and true zero values; create route')
    await context.close()
  }
  {
    const { context, page, state, calls } = await setup()
    state.roleFailure = true
    await page.goto(base)
    await page.getByText('无法确认访问权限', { exact: true }).waitFor()
    assert.equal(
      calls.filter((call) => call.path === '/system/status').length,
      0,
    )
    state.roleFailure = false
    state.role = 'admin'
    await page.getByRole('button', { name: /^重\s*试$/ }).click()
    await page.getByText('降级', { exact: true }).waitFor()
    report.checks.push('role failure and permission retry')
    await context.close()
  }
  {
    const { context, page, state } = await setup()
    let release
    state.gate = new Promise((resolve) => {
      release = resolve
    })
    await page.goto(base)
    await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
    assert.equal(
      await page.getByRole('table', { name: '最近评估', exact: true }).count(),
      0,
    )
    assert.ok((await page.locator('[aria-busy="true"]').count()) > 0)
    await page.evaluate(async () => {
      const { useAuthStore } = await import('/src/store/auth.ts')
      useAuthStore.setState({
        session: {
          marker: 'new-owner',
          username: 'new-user',
          expiresAt: Date.now() + 3600000,
        },
      })
    })
    state.total = 0
    state.gate = null
    release()
    await page.getByText('还没有评估任务', { exact: true }).waitFor()
    assert.equal(
      await page
        .locator('.dashboard-page')
        .getByText('real-model-with-long-model-name-32B')
        .count(),
      0,
    )
    report.checks.push(
      'loading feedback and late-response isolation across session change',
    )
    await context.close()
  }
  assert.deepEqual(report.errors, [])
  report.pass = true
} catch (error) {
  report.pass = false
  report.failure = error.stack
  throw error
} finally {
  await writeFile(
    resolve(output, 'report.json'),
    JSON.stringify(report, null, 2),
  )
  await browser.close()
  console.log(
    JSON.stringify({ pass: report.pass, checks: report.checks.length, output }),
  )
}
