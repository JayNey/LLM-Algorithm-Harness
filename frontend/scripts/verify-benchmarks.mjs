/* global localStorage */
// 基准 Suite 与 A/B 测试页验证（issue #166 第②步）——浏览器 fixture 层。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import process from 'node:process'
import console from 'node:console'

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.BENCHMARK_BASE_URL || 'http://127.0.0.1:5180'
const outDir =
  process.env.BENCHMARK_QA_DIR ||
  resolve(
    process.cwd(),
    '../docs/superpowers/reports/assets/benchmarks/fixture',
  )

const known = ['suites', 'curve', 'abtests', 'all']
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
        report.assertions[index].error = String(error)
      },
    )
}

const suiteFixture = {
  id: 'suite-fixture-1',
  name: '学习曲线套件',
  version: '1.0',
  description: null,
  frozen: false,
  problems: ['p1', 'p2'],
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:00:00Z',
}
const keys = [
  {
    id: 'key-fixture-1',
    provider: 'siliconflow',
    key_name: '冒烟密钥',
    created_at: 0,
    last_used_at: null,
    usage_count: 0,
    verified: true,
    masked_preview: 'sk-***',
  },
]

const abJobFixture = {
  id: 'ab-fixture-1',
  name: '提示词对比',
  status: 'completed',
  task_id: null,
  config: {
    name: '提示词对比',
    dataset_path: 'datasets/demo.json',
    model: { model: 'model-a' },
    strategy: { name: 'direct' },
    prompt_variants: [{ id: 'baseline' }, { id: 'treatment' }],
    seed: 42,
    max_workers: 4,
    api_key_id: 'key-fixture-1',
  },
  error_message: null,
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:05:00Z',
}

function mockRoute(context) {
  context.route('**/api/v1/**', (route, request) => {
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    // 应用 dev 环境直连 :8000（跨源且 withCredentials），fulfill 响应必须
    // 反射具体 origin 并携带 allow-credentials，'*' 会被浏览器拦截。
    const cors = {
      'access-control-allow-origin': request.headers()['origin'] ?? '*',
      'access-control-allow-credentials': 'true',
    }
    if (method === 'OPTIONS')
      return route.fulfill({
        status: 204,
        headers: {
          ...cors,
          'access-control-allow-headers': '*',
          'access-control-allow-methods': 'GET,POST,PATCH,DELETE,OPTIONS',
        },
      })
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        headers: { ...cors },
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data, message: '' }),
      })
    report.replaced.push(`${method} ${path}`)
    if (method === 'GET' && path === '/users/me')
      return reply({ id: 'user-fixture-1', username: 'fixture', role: 'user' })
    if (method === 'GET' && path === '/api-keys') return reply(keys)
    if (method === 'GET' && path === '/evaluation-options')
      return reply({
        strategies: [{ name: 'vanilla' }, { name: 'chain_of_thought' }],
        sources: [{ id: 'shared', label: '共享题库', problem_count: 2 }],
      })
    if (
      method === 'GET' &&
      path === '/evaluation-options/models' &&
      url.searchParams.get('api_key_id') === 'key-fixture-1'
    )
      return reply({
        provider: 'siliconflow',
        models: ['model-a', 'model-b'],
        complete: true,
      })
    if (method === 'GET' && path === '/benchmarks/suites')
      return reply({
        items: [suiteFixture],
        total: 1,
        limit: 1,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/benchmarks/suites/suite-fixture-1')
      return reply(suiteFixture)
    if (method === 'GET' && path === '/ab-tests/ab-fixture-1')
      return reply(abJobFixture)
    if (method === 'POST' && path === '/benchmarks/suites')
      return reply({ ...suiteFixture, id: 'suite-fixture-new' }, 201)
    if (
      method === 'GET' &&
      path === '/benchmarks/learning-curve/suite-fixture-1'
    )
      return reply({
        suite_id: 'suite-fixture-1',
        suite_name: '学习曲线套件',
        data: [
          {
            timestamp: '2026-10-22T00:00:00Z',
            model: 'model-a',
            accuracy: 0.5,
            cost_usd: 0.01,
          },
          {
            timestamp: '2026-10-23T00:00:00Z',
            model: 'model-a',
            accuracy: 0.75,
            cost_usd: 0.03,
          },
        ],
        trends: { accuracy_growth_rate: 0.5, cost_growth_rate: 2.0 },
      })
    if (method === 'GET' && path === '/tasks')
      return reply({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/ab-tests')
      return reply({
        items: [abJobFixture],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/ab-tests/ab-fixture-1/results')
      return reply({
        name: '提示词对比',
        generated_at: '2026-10-23T00:10:00Z',
        variants: [
          { id: 'baseline', description: '' },
          { id: 'treatment', description: '' },
        ],
        baseline_id: 'baseline',
        treatment_id: 'treatment',
        comparison: {
          sample: {
            baseline: 0.5,
            treatment: 0.75,
            ci95: { difference: 0.25, lower: -0.1, upper: 0.6 },
          },
          formal: {
            baseline: 0.5,
            treatment: 0.8,
            ci95: { difference: 0.3, lower: -0.05, upper: 0.65 },
          },
          statistics: {
            categorical_test: 'fisher_exact',
            p_value: 0.5,
            welch_t_p_value: 0.42,
          },
          elapsed_seconds: { baseline: 5.1, treatment: 4.8 },
          tokens: { baseline: 600, treatment: 600 },
          failure_categories: { baseline: {}, treatment: {} },
        },
      })
    report.unknown.push(`${method} ${path}`)
    return route.fulfill({
      status: 599,
      contentType: 'application/json',
      body: '{}',
    })
  })
}

async function suitesScenario(page) {
  await page.goto(`${base}/benchmarks`)
  await check('套件列表渲染', async () => {
    await page.waitForSelector('table[aria-label="基准套件列表"]')
    assert.ok((await page.getByText('学习曲线套件').count()) >= 1)
  })
  await page.screenshot({ path: resolve(outDir, 'suites.png'), fullPage: true })
  report.screenshots.push('suites.png')
}

async function curveScenario(page) {
  await page.goto(`${base}/benchmarks/suite-fixture-1`)
  await check('学习曲线 Tab 渲染趋势', async () => {
    await page.getByRole('tab', { name: '学习曲线' }).click()
    await page.waitForSelector('text=准确率增长：+50.0%')
    assert.ok(true)
  })
  await page.screenshot({ path: resolve(outDir, 'curve.png'), fullPage: true })
  report.screenshots.push('curve.png')
}

async function abtestsScenario(page) {
  await page.goto(`${base}/ab-tests`)
  await check('AB 列表渲染', async () => {
    await page.waitForSelector('table[aria-label="A/B 测试列表"]')
    assert.ok((await page.getByText('ab-fixture-1').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'abtests.png'),
    fullPage: true,
  })
  report.screenshots.push('abtests.png')
}

async function abDetailScenario(page) {
  await page.goto(`${base}/ab-tests/ab-fixture-1`)
  await check('AB 结果统计表渲染', async () => {
    await page.waitForSelector('table[aria-label="A/B 通过率对比"]')
    assert.ok((await page.getByText('Fisher 精确检验').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'ab-detail.png'),
    fullPage: true,
  })
  report.screenshots.push('ab-detail.png')
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
        marker: 'fixture-user',
        username: 'fixture',
        expiresAt: Date.now() + 3_600_000,
      }),
    )
  })
  mockRoute(context)
  const page = await context.newPage()
  if (scenario === 'all' || scenario === 'suites') await suitesScenario(page)
  if (scenario === 'all' || scenario === 'curve') await curveScenario(page)
  if (scenario === 'all' || scenario === 'abtests') await abtestsScenario(page)
  if (scenario === 'all') await abDetailScenario(page)
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
