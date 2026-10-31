/* global localStorage, document, window */
// Browser fixtures. Real TCP HTTP acceptance runs separately.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
import { setTimeout } from 'node:timers'
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || 'playwright',
)
const base = process.env.BENCHMARK_BASE_URL || 'http://127.0.0.1:5201'
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
let assertions = 0
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
  })
  await context.addInitScript(() =>
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'fixture',
        username: 'fixture',
        expiresAt: Date.now() + 3600000,
      }),
    ),
  )
  const page = await context.newPage(),
    exceptions = [],
    unknown = []
  page.on('pageerror', (e) => exceptions.push(String(e)))
  const row = (id, status = 'completed') => ({
    id,
    suite_id: 'suite',
    task_id: status === 'completed' ? null : `task-${id}`,
    status,
    model: 'test-model',
    accuracy: status === 'completed' ? 0.5 : null,
    cost_usd: null,
    error_message: null,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:01:00Z',
    results: { actual: 'persisted' },
  })
  let releaseLaunch
  let activeStatus = 'running',
    pausedStatus = 'paused',
    historyCalls = 0,
    curveCalls = 0,
    taskCalls = 0
  await context.route('**/api/v1/**', async (route, request) => {
    const url = new URL(request.url()),
      path = url.pathname.replace('/api/v1', '')
    const headers = {
      'access-control-allow-origin': new URL(base).origin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers':
        'content-type,x-csrf-token,x-requested-with',
      'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
    }
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        headers,
        contentType: 'application/json',
        body: JSON.stringify({
          success: status < 400,
          data,
          message: status < 400 ? '' : 'Not found',
        }),
      })
    if (request.method() === 'OPTIONS')
      return route.fulfill({ status: 204, headers })
    if (path === '/users/me')
      return reply({ id: 'fixture', username: 'fixture', role: 'user' })
    if (path === '/api-keys')
      return reply([
        {
          id: 'key',
          provider: 'openai',
          key_name: 'Test key',
          created_at: 0,
          last_used_at: null,
          usage_count: 0,
          verified: true,
          masked_preview: 'sk-***',
        },
      ])
    if (path === '/datasets')
      return reply([
        { id: 'mine', name: 'Personal', problem_count: 1, updated_at: 0 },
      ])
    if (path === '/evaluation-options/models')
      return reply({
        provider: 'openai',
        models: ['test-model'],
        complete: true,
        source: 'provider_api',
        scope: 'evaluation',
      })
    if (
      path === '/benchmarks/suites/suite/run' &&
      request.method() === 'POST'
    ) {
      await new Promise((resolve) => {
        releaseLaunch = resolve
      })
      return reply(row('new-run', 'pending'), 202)
    }

    if (path === '/evaluation-options')
      return reply({ strategies: [{ name: 'vanilla' }], sources: [] })
    if (path === '/benchmarks/suites/suite')
      return reply({
        id: 'suite',
        name: 'History suite',
        version: '1.0',
        description: null,
        frozen: false,
        problems: ['p1'],
        created_at: '2026-11-01T00:00:00Z',
        updated_at: '2026-11-01T00:00:00Z',
      })
    if (path === '/benchmarks/suites/suite/runs') {
      historyCalls++
      const status = url.searchParams.get('status'),
        offset = Number(url.searchParams.get('offset') || 0),
        limit = Number(url.searchParams.get('limit') || 20)
      const all = Array.from({ length: 25 }, (_, i) => row(`history-${i}`))
      const rows =
        status === 'running'
          ? activeStatus === 'running'
            ? [row('active', 'running')]
            : []
          : status === 'paused'
            ? [row('paused', 'paused')]
            : status
              ? all.filter((r) => r.status === status)
              : all
      return reply({
        items: rows.slice(offset, offset + limit),
        total: rows.length,
        limit,
        offset,
        has_more: offset + limit < rows.length,
      })
    }
    if (path === '/benchmarks/learning-curve/suite') {
      curveCalls++
      return reply({
        suite_id: 'suite',
        suite_name: 'History suite',
        data: [
          {
            run_id: 'outside',
            timestamp: '2026-11-01T00:00:00Z',
            model: 'test-model',
            accuracy: 0.5,
            cost_usd: null,
          },
        ],
        trends: { accuracy_growth_rate: null, cost_growth_rate: null },
      })
    }
    if (path.startsWith('/benchmarks/runs/')) {
      const id = decodeURIComponent(path.split('/').at(-1))
      if (id === 'missing') return reply(null, 404)
      if (id === 'foreign') return reply({ ...row(id), suite_id: 'other' })
      if (id === 'bad-paused') return reply(row(id, 'paused'))
      if (id === 'slow')
        await new Promise((resolve) => setTimeout(resolve, 600))
      return reply(
        row(
          id,
          id === 'active'
            ? activeStatus
            : id === 'paused'
              ? pausedStatus
              : id === 'bad-task'
                ? 'running'
                : 'completed',
        ),
      )
    }
    if (path.startsWith('/tasks/')) {
      taskCalls++
      const id = path.slice('/tasks/task-'.length)
      return reply({
        id: `task-${id}`,
        entity_id: id.startsWith('bad-') ? 'foreign-run' : id,
        task_type: 'benchmark',
        status: id === 'active' ? activeStatus : pausedStatus,
        progress: { current: 1, total: 2, percentage: 50, current_step: 'p1' },
        error_message: null,
      })
    }
    unknown.push(path)
    return reply(null, 404)
  })
  await page.goto(`${base}/benchmarks/suite?run_id=outside&view=compact`)
  await page
    .getByRole('heading', { name: '运行历史', exact: true })
    .waitFor({ timeout: 5000 })
  assertions++
  if (process.argv.includes('--red-probe'))
    throw new Error('RED probe unexpectedly found history UI')
  await page.getByRole('heading', { name: '选中运行', exact: true }).waitFor()
  assert.match(
    await page.getByTestId('selected-benchmark-run').innerText(),
    /outside/,
  )
  assertions++
  await page.reload()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText('outside', { exact: true })
    .waitFor()
  assertions++
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.getByRole('link', { name: 'history-20', exact: true }).waitFor()
  assert.equal(new URL(page.url()).searchParams.get('run_id'), 'outside')
  assert.equal(new URL(page.url()).searchParams.get('view'), 'compact')
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=outside&view=kept`)
  const pick = async (label, option) => {
    await page.getByLabel(label, { exact: true }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText(option, { exact: true })
      .last()
      .click()
  }
  await pick('基准运行密钥', 'Test key')
  await pick('选择个人题库', '个人题库 · 1 题')
  await pick('基准运行模型', 'test-model')
  const started = page.waitForRequest(
    (r) =>
      r.method() === 'POST' && r.url().endsWith('/benchmarks/suites/suite/run'),
  )
  await page.getByRole('button', { name: '启动基准运行', exact: true }).click()
  await started
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.getByRole('link', { name: 'history-20', exact: true }).waitFor()
  assert.equal(typeof releaseLaunch, 'function')
  releaseLaunch()
  await page.waitForURL((u) => u.searchParams.get('run_id') === 'new-run')
  assert.equal(new URL(page.url()).searchParams.get('offset'), '20')
  assert.equal(new URL(page.url()).searchParams.get('view'), 'kept')
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=missing`)
  await page.getByTestId('selected-benchmark-run').getByRole('alert').waitFor()
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=foreign`)
  await page.getByText('运行关联不匹配，请重新选择', { exact: true }).waitFor()
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=bad-task`)
  await page
    .getByText('任务关联不匹配，已停止进度查询', { exact: true })
    .waitFor({ timeout: 8500 })
  const badCalls = taskCalls
  await page.waitForTimeout(3300)
  assert.equal(taskCalls, badCalls)
  assertions++
  await page.goto(`${base}/benchmarks/suite`)
  await page.getByRole('link', { name: 'paused', exact: true }).waitFor()
  assert.equal(new URL(page.url()).searchParams.get('run_id'), null)
  assertions++
  await page.getByRole('link', { name: 'paused', exact: true }).click()
  await page
    .getByText('任务已暂停，可手动刷新运行状态', { exact: true })
    .waitFor()
  const pausedCalls = taskCalls
  await page.waitForTimeout(3300)
  assert.equal(taskCalls, pausedCalls)
  assertions++
  pausedStatus = 'running'
  await page.getByRole('button', { name: '刷新运行', exact: true }).click()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText(/^运行中 ·/)
    .waitFor()
  await page.waitForTimeout(300)
  assert.equal(
    await page
      .getByText('进度查询已中断，请刷新运行重试', { exact: true })
      .count(),
    0,
  )
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=bad-paused`)
  await page
    .getByText('任务关联不匹配，已停止进度查询', { exact: true })
    .waitFor({ timeout: 4000 })
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=active`)
  await page.getByTestId('selected-benchmark-run').getByText(/50%/).waitFor()
  const beforeHistory = historyCalls,
    beforeCurve = curveCalls
  activeStatus = 'completed'
  await page.getByRole('button', { name: '刷新运行', exact: true }).click()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText(/^已完成 ·/)
    .waitFor()
  await page.waitForTimeout(500)
  assert.ok(historyCalls > beforeHistory && curveCalls > beforeCurve)
  assertions++
  const terminalCalls = taskCalls
  await page.waitForTimeout(3300)
  assert.equal(taskCalls, terminalCalls)
  assertions++
  await page.goto(`${base}/benchmarks/suite?run_id=slow`)
  await page.waitForTimeout(80)
  await page.goto(`${base}/benchmarks/suite?run_id=outside`)
  await page.waitForTimeout(800)
  const selected = await page.getByTestId('selected-benchmark-run').innerText()
  assert.match(selected, /outside/)
  assert.doesNotMatch(selected, /slow/)
  assertions++
  await page.getByRole('tab', { name: '学习曲线', exact: true }).click()
  await page.getByRole('link', { name: /test-model.*outside/ }).click()
  assert.equal(new URL(page.url()).searchParams.get('run_id'), 'outside')
  assertions++
  await page.setViewportSize({ width: 320, height: 800 })
  await page.goto(`${base}/benchmarks/suite?run_id=outside`)
  await page.getByTestId('selected-benchmark-run').waitFor()
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  )
  assertions++
  await context.addInitScript(() =>
    localStorage.setItem('llm-harness-language', 'en-US'),
  )
  await page.reload()
  await page
    .getByRole('heading', { name: 'Run history', exact: true })
    .waitFor()
  assertions++
  assert.deepEqual(exceptions, [])
  assert.deepEqual(unknown, [])
  console.log(
    JSON.stringify({
      layer: 'browser-fixture',
      assertions,
      exceptions,
      unknown,
    }),
  )
} finally {
  await browser.close()
}
