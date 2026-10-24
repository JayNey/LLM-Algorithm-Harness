/* global localStorage */
// 题目管理页验证（issue #163）——浏览器 fixture 层。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import { Buffer } from 'node:buffer'
import process from 'node:process'
import console from 'node:console'

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.PROBLEM_BASE_URL || 'http://127.0.0.1:5180'
const outDir =
  process.env.PROBLEM_QA_DIR ||
  resolve(process.cwd(), '../docs/superpowers/reports/assets/problems/fixture')

const known = ['list', 'import', 'history', 'all']
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
        username: 'fixture',
        role: 'user',
        email: 'f@e.org',
        created_at: '2026-10-24',
      })
    if (method === 'GET' && path === '/api-keys') return reply(keys)
    if (method === 'GET' && path === '/evaluation-options')
      return reply({
        strategies: [{ name: 'direct' }],
        sources: [
          { id: 'shared', label: '共享题目', problem_count: 2 },
          { id: 'personal', label: '个人题目', problem_count: 1 },
        ],
      })
    if (method === 'GET' && path === '/evaluation-options/problems') {
      const source = url.searchParams.get('source') ?? 'all'
      const shared = [
        {
          problem_id: 'shared-1',
          title: '共享题一',
          difficulty: 'easy',
          source: 'shared',
        },
        {
          problem_id: 'shared-2',
          title: '共享题二',
          difficulty: 'hard',
          source: 'shared',
        },
      ]
      const personal = [
        {
          problem_id: 'mine-1',
          title: '个人题一',
          difficulty: null,
          source: 'personal',
        },
      ]
      const items =
        source === 'shared'
          ? shared
          : source === 'personal'
            ? personal
            : [...personal, ...shared]
      return reply({
        items,
        total: items.length,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    }
    if (method === 'POST' && path === '/problems/upload')
      return reply(
        {
          file_id: 'f-import-1',
          job_id: 'j-import-1',
          validation: {
            total: 3,
            valid: 2,
            invalid: 1,
            errors: [{ index: 1, error: 'description: missing' }],
            errors_truncated: false,
            file_id: 'f-import-1',
            duplicates: 1,
            imported: 2,
            dataset_total: 4,
          },
        },
        201,
      )
    if (method === 'GET' && path.startsWith('/results/problems/'))
      return reply({
        items: [
          {
            problem_id: 'mine-1',
            strategy: 'direct',
            status: 'passed',
            iterations: 1,
            tokens: 100,
            execution_time: 0.5,
            run_id: 'r1',
          },
          {
            problem_id: 'mine-1',
            strategy: 'reflexion',
            status: 'error',
            iterations: null,
            tokens: null,
            execution_time: null,
            run_id: null,
          },
        ],
        total: 2,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    report.unknown.push(`${method} ${path}`)
    return route.fulfill({
      status: 599,
      contentType: 'application/json',
      body: '{}',
    })
  })
}

async function listScenario(page) {
  await page.goto(`${base}/problems`)
  await check('题目列表渲染元数据行', async () => {
    await page.waitForSelector('table[aria-label="题目列表"]')
    assert.ok((await page.getByText('共享题一').count()) >= 1)
    assert.ok((await page.getByText('mine-1').count()) >= 1)
  })
  await check('来源筛选切到个人', async () => {
    await page.getByLabel('题目来源').click()
    await page.getByRole('option', { name: /个人题目/ }).click()
    await page.waitForSelector('text=个人题一')
    assert.ok(page.url().includes('source=personal'))
    assert.equal(await page.getByText('共享题一').count(), 0)
  })
  await page.screenshot({ path: resolve(outDir, 'list.png'), fullPage: true })
  report.screenshots.push('list.png')
}

async function importScenario(page) {
  await page.goto(`${base}/problems`)
  await page.getByRole('button', { name: '导入题目' }).click()
  await check('同步导入报告呈现', async () => {
    await page.setInputFiles('input[type="file"]', {
      name: 'problems.json',
      mimeType: 'application/json',
      buffer: Buffer.from('[]'),
    })
    await page.getByLabel('导入模式').click()
    await page.getByRole('option', { name: /追加/ }).click()
    await page.getByRole('button', { name: '开始导入' }).click()
    await page.waitForSelector('[aria-label="导入报告"]')
    assert.ok((await page.getByText('无效 1').count()) >= 1)
    assert.ok((await page.getByText('重复 1').count()) >= 1)
    assert.ok((await page.getByText('第 2 条').count()) >= 1)
  })
  await page.screenshot({ path: resolve(outDir, 'import.png'), fullPage: true })
  report.screenshots.push('import.png')
}

async function historyScenario(page) {
  await page.goto(`${base}/problems`)
  await check('评估历史抽屉聚合', async () => {
    await page.getByRole('button', { name: '评估历史' }).first().click()
    await page.waitForSelector('table[aria-label="题目评估历史"]')
    assert.ok((await page.getByText('通过率 50%').count()) >= 1)
    assert.ok((await page.getByText('执行错误').count()) >= 1)
  })
  await page.screenshot({
    path: resolve(outDir, 'history.png'),
    fullPage: true,
  })
  report.screenshots.push('history.png')
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
  if (scenario === 'all' || scenario === 'list') await listScenario(page)
  if (scenario === 'all' || scenario === 'import') await importScenario(page)
  if (scenario === 'all' || scenario === 'history') await historyScenario(page)
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
