/* global localStorage */
// 设置与系统管理页验证（issue #167）——浏览器 fixture 层。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import process from 'node:process'
import console from 'node:console'

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.SETTINGS_BASE_URL || 'http://127.0.0.1:5180'
const outDir =
  process.env.SETTINGS_QA_DIR ||
  resolve(process.cwd(), '../docs/superpowers/reports/assets/settings/fixture')

const known = ['monitor', 'budgets', 'pricing', 'logs', 'all']
const scenario = process.argv[2] || 'all'
assert.ok(known.includes(scenario), `未知场景：${scenario}`)

const report = {
  scenario,
  layer: 'browser-fixture (not backend E2E)',
  assertions: [],
  replaced: [],
  unknown: [],
  screenshots: [],
}

function check(name, fn) {
  report.assertions.push({ name, ok: false })
  const index = report.assertions.length - 1
  return Promise.resolve()
    .then(fn)
    .then(
      () => {
        report.assertions[index].ok = true
      },
      (error) => {
        report.assertions[index].pass = false
        report.assertions[index].error = String(error)
        throw error
      },
    )
}

function mockRoute(context) {
  context.route('**/api/v1/**', (route, request) => {
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        headers: { 'access-control-allow-origin': '*' },
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data, message: '' }),
      })
    report.replaced.push(`${method} ${path}`)
    if (method === 'GET' && path === '/users/me')
      return reply({
        username: 'admin-fixture',
        role: 'admin',
        email: 'a@e.org',
        created_at: '2026-10-24',
      })
    if (method === 'GET' && path === '/system/status')
      return reply({
        uptime_seconds: 3600,
        task_counts: { pending: 1, running: 1, completed: 3 },
        task_count: 5,
        task_status: 'ok',
        task_source: 'monitor_store',
        async_task_counts: { pending: 1, running: 0, completed: 4 },
        async_task_count: 5,
        async_task_status: 'ok',
        async_task_source: 'async_task',
        health: {
          status: 'healthy',
          checks: {
            database: { status: 'ok' },
            redis: {
              status: 'ok',
              broker_queue: {
                status: 'ok',
                waiting: 2,
                queues: [{ name: 'default', waiting: 2 }],
              },
            },
            workers: { status: 'ok', worker_count: 2, active: 1, reserved: 0 },
            sandbox: { status: 'ok' },
          },
        },
        resources: {
          cpu: { status: 'ok', percent: 25.5, sample_seconds: 0.1 },
          memory: {
            status: 'ok',
            total_bytes: 8e9,
            available_bytes: 4e9,
            used_bytes: 4e9,
            percent: 50,
          },
          disk: {
            status: 'ok',
            total_bytes: 1e11,
            used_bytes: 5e10,
            free_bytes: 5e10,
            percent: 50,
          },
        },
        workers: { status: 'ok', worker_count: 2, active: 1, reserved: 0 },
        queue_metrics: {
          broker_queue: {
            status: 'ok',
            waiting: 2,
            queues: [{ name: 'default', waiting: 2 }],
          },
          database_pending: { status: 'ok', count: 1 },
          worker_reserved: { status: 'ok', count: 0 },
        },
        containers: { status: 'not_configured' },
      })
    if (method === 'GET' && path === '/metrics/api-stats')
      return reply({
        request_count: 100,
        errors: 2,
        error_rate: 0.02,
        avg_response_time_ms: 40,
        p95_response_time_ms: 150,
        requests_per_second: 0.5,
        window_complete: true,
        window_seconds: Number(url.searchParams.get('window_seconds') ?? 60),
      })
    if (method === 'GET' && path === '/metrics/llm-stats')
      return reply({
        status: 'ok',
        total_calls: 10,
        successful_calls: 9,
        failed_calls: 1,
        success_rate: 0.9,
        avg_latency_ms: 300,
        window_seconds: Number(url.searchParams.get('window_seconds') ?? 3600),
        window_complete: true,
      })
    if (method === 'GET' && path === '/metrics/cache-stats')
      return reply({
        enabled: true,
        total_entries: 20,
        disk_usage_mb: 1.5,
        hit_rate: 0.6,
        hits: 12,
        misses: 8,
        api_calls_saved: 12,
      })
    if (method === 'GET' && path === '/budgets')
      return reply({
        global_cap_usd: 100,
        difficulty_caps: { easy: 30, medium: null, hard: 20 },
        action: 'pause',
      })
    if (method === 'PATCH' && path === '/budgets')
      return reply({
        global_cap_usd: 200,
        difficulty_caps: { easy: 50 },
        action: 'downgrade',
      })
    if (method === 'GET' && path === '/budgets/usage')
      return reply({
        global_budget: {
          cap_usd: 100,
          used_usd: 40,
          remaining_usd: 60,
          percentage_used: 40,
        },
        by_difficulty: {
          easy: { cap_usd: 30, used_usd: 10, percentage_used: 33.33 },
          medium: { cap_usd: null, used_usd: 0, percentage_used: null },
          hard: { cap_usd: 20, used_usd: 0, percentage_used: 0 },
        },
        basis: 'estimate',
      })
    if (method === 'GET' && path === '/alerts')
      return reply([
        {
          id: 'rule-1',
          name: '预算预警',
          threshold_pct: 80,
          channel: 'webhook',
          target: 'https://example.com (已脱敏)',
          enabled: true,
          created_at: '2026-10-24T00:00:00Z',
          updated_at: '2026-10-24T00:00:00Z',
        },
      ])
    if (method === 'GET' && path === '/pricing')
      return reply({
        models: {
          'model-builtin': {
            prompt_per_1k: 0.5,
            completion_per_1k: 1.5,
            source: 'builtin',
          },
          'model-override': {
            prompt_per_1k: 0.2,
            completion_per_1k: 0.6,
            source: 'override',
          },
        },
      })
    if (method === 'GET' && path.startsWith('/pricing/'))
      return reply([
        {
          prompt_per_1k: 0.2,
          completion_per_1k: 0.6,
          created_by: 'admin-fixture',
          created_at: '2026-10-24T00:00:00Z',
        },
      ])
    if (method === 'GET' && path === '/logs')
      return reply({
        items: [
          {
            id: 2,
            timestamp: 1760000002.5,
            level: 'ERROR',
            message: '任务失败',
            user_id: 'u1',
            run_id: null,
            context: {},
          },
          {
            id: 1,
            timestamp: 1760000001,
            level: 'INFO',
            message: '请求完成',
            user_id: null,
            run_id: 'r1',
            context: {},
          },
        ],
        total: 2,
        limit: 50,
        offset: 0,
        source: 'retained_api_and_task_events',
      })
    if (method === 'GET' && path === '/config/sandbox')
      return reply({
        backend: 'docker',
        docker_image: 'python:3.11-slim',
        timeout_seconds: 5,
        memory_limit_mb: 256,
        max_output_bytes: 1024,
        max_processes: 1,
        allowed_imports: ['math'],
      })
    if (method === 'GET' && path === '/config/strategies')
      return reply({
        strategies: [{ name: 'vanilla', defaults: { temperature: 0.7 } }],
      })
    if (method === 'GET' && path === '/config/providers')
      return reply({
        status: 'ok',
        scope: 'offline_example_catalog',
        live_provider_availability_checked: false,
        providers: [
          { provider: 'openai', models: ['gpt-4o-mini'] },
          { provider: 'siliconflow', models: [] },
        ],
      })
    report.unknown.push(`${method} ${path}`)
    return route.fulfill({
      status: 599,
      contentType: 'application/json',
      body: '{}',
    })
  })
}

async function monitorScenario(page) {
  await page.goto(`${base}/settings/system`)
  await check('监控面板分区渲染（健康/资源/统计）', async () => {
    await page.getByRole('tab', { name: '概览' }).waitFor()
    assert.ok((await page.getByText('正常').count()) >= 1)
    await page.getByRole('tab', { name: '统计' }).click()
    await page.getByText('平均 / P95 响应').waitFor()
    assert.ok((await page.getByText('40 ms').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'monitor.png'),
    fullPage: true,
  })
  report.screenshots.push('monitor.png')
}

async function budgetsScenario(page) {
  await page.goto(`${base}/settings/budgets`)
  await check('预算使用量与预警规则渲染（含投递未实现提示）', async () => {
    await page.getByText('预算使用量').waitFor()
    assert.ok((await page.getByText('40%').count()) >= 1)
    assert.ok((await page.getByText('预算预警').count()) >= 1)
    assert.ok((await page.getByText('通知投递后端尚未实现').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'budgets.png'),
    fullPage: true,
  })
  report.screenshots.push('budgets.png')
}

async function pricingScenario(page) {
  await page.goto(`${base}/settings/pricing`)
  await check('定价目录三源标注渲染', async () => {
    await page.getByRole('table', { name: '定价目录' }).waitFor()
    assert.ok((await page.getByText('内置').count()) >= 1)
    assert.ok((await page.getByText('覆盖').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'pricing.png'),
    fullPage: true,
  })
  report.screenshots.push('pricing.png')
}

async function logsScenario(page) {
  await page.goto(`${base}/settings/logs`)
  await check('日志查询渲染（级别/消息/运行）', async () => {
    await page.getByRole('table', { name: '系统日志' }).waitFor()
    assert.ok((await page.getByText('任务失败').count()) >= 1)
    assert.ok((await page.getByText('r1').count()) >= 1)
  })
  await page.screenshot({ path: resolve(outDir, 'logs.png'), fullPage: true })
  report.screenshots.push('logs.png')
}

const { chromium } = playwright
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
try {
  const context = await browser.newContext()
  await context.addInitScript(() => {
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'admin-fixture',
        username: 'admin-fixture',
        expiresAt: Date.now() + 3_600_000,
      }),
    )
  })
  mockRoute(context)
  const page = await context.newPage()
  if (scenario === 'all' || scenario === 'monitor') await monitorScenario(page)
  if (scenario === 'all' || scenario === 'budgets') await budgetsScenario(page)
  if (scenario === 'all' || scenario === 'pricing') await pricingScenario(page)
  if (scenario === 'all' || scenario === 'logs') await logsScenario(page)
  await check('无未声明 API 请求', () => assert.deepEqual(report.unknown, []))
} finally {
  const { writeFileSync, mkdirSync } = await import('node:fs')
  mkdirSync(outDir, { recursive: true })
  writeFileSync(
    resolve(outDir, `${scenario}.json`),
    JSON.stringify(report, null, 2),
  )
  const failed = report.assertions.filter((item) => !item.ok)
  console.log(
    `scenario=${scenario} assertions=${report.assertions.length} failed=${failed.length} unknown=${report.unknown.length}`,
  )
  await browser.close()
  if (failed.length) process.exitCode = 1
}
