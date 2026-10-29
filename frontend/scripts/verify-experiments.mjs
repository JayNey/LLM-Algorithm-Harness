/* global localStorage */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import process from 'node:process'
import { URL } from 'node:url'
import console from 'node:console'
// 实验管理前端验证脚本（issue #166 第①步）——浏览器 fixture 层，
// 不连接真实后端；运行方式见 docs/frontend/QA.md。

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.EXPERIMENT_BASE_URL || 'http://127.0.0.1:5180'
const outDir =
  process.env.EXPERIMENT_QA_DIR ||
  resolve(
    process.cwd(),
    '../docs/superpowers/reports/assets/experiments/fixture',
  )

const known = ['create', 'list', 'detail', 'all']
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

const fixtureJob = {
  id: 'exp-fixture-1',
  name: '对比实验',
  status: 'pending',
  config: {
    name: '对比实验',
    dataset_path: 'datasets/demo.json',
    models: [{ model: 'model-a', temperature: 0.7 }],
    strategies: [{ name: 'direct' }],
    repeats: 1,
    budget: { max_calls: 10 },
    execution: 'serial',
    max_workers: 4,
  },
  error_message: null,
  created_at: '2026-10-22T00:00:00Z',
  updated_at: '2026-10-22T00:01:00Z',
}
const fixtureKeys = [
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

const fixtureOptions = {
  strategies: [{ name: 'direct' }, { name: 'chain_of_thought' }],
  sources: [{ id: 'shared', label: '共享题库', problem_count: 2 }],
}
const fixtureModels = {
  provider: 'siliconflow',
  models: ['model-a', 'model-b'],
  complete: true,
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
    if (method === 'GET' && path === '/datasets') return reply([])
    if (method === 'GET' && path === '/users/me')
      return reply({ id: 'user-fixture-1', username: 'fixture', role: 'user' })
    if (method === 'GET' && path === '/api-keys') return reply(fixtureKeys)
    if (method === 'GET' && path === '/evaluation-options')
      return reply(fixtureOptions)
    if (
      method === 'GET' &&
      path === '/evaluation-options/models' &&
      url.searchParams.get('api_key_id') === 'key-fixture-1'
    )
      return reply(fixtureModels)
    if (
      method === 'GET' &&
      path === '/experiments' &&
      url.searchParams.get('status') !== 'completed'
    )
      return reply({
        items: [fixtureJob],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (method === 'POST' && path === '/experiments') {
      report.experimentPost = JSON.parse(request.postData() ?? 'null')
      return reply(
        {
          ...fixtureJob,
          id: 'exp-fixture-new',
          created_at: '2026-10-22T01:00:00Z',
        },
        201,
      )
    }
    if (method === 'GET' && path === '/experiments/exp-fixture-new')
      return reply({ ...fixtureJob, id: 'exp-fixture-new' })
    if (method === 'GET' && path === '/experiments/exp-fixture-1')
      return reply(fixtureJob)
    if (method === 'GET' && path === '/tasks')
      return reply({
        items: [],
        total: 0,
        limit: 100,
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

async function createScenario(page) {
  await page.goto(`${base}/experiments/new`)
  await check('创建页渲染标题', async () => {
    await page.getByRole('heading', { name: '创建实验' }).waitFor()
    assert.equal(
      await page.getByRole('heading', { name: '创建实验' }).count(),
      1,
    )
  })
  await page.getByLabel('实验名称').fill('对比实验')
  await page.getByLabel('数据来源', { exact: true }).click()
  await page
    .locator('.ant-select-dropdown:visible')
    .getByText('服务器数据集路径', { exact: true })
    .click()
  await page
    .getByLabel('数据集路径', { exact: true })
    .fill('datasets/demo.json')
  await page.getByLabel('实验 API Key').click()
  // antd 虚拟列表在并发目录请求落地的重渲染下可能把选项测成 0 宽，
  // 点击式选option不稳定，改用键盘选择。
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  // rc-select 的无障碍 listbox 只渲染激活项附近的窄窗口，getByRole('option')
  // 会漏掉非激活项；目录断言按可视选项节点定位，并用输入触发下拉（点击开合
  // 在连续交互下不稳定）。
  const catalogOption = (name) =>
    page.locator('.ant-select-item-option', { hasText: name })
  await check('模型字段提供密钥对应的真实目录', async () => {
    await page.getByLabel('模型 1 名称').fill('model-')
    await catalogOption('model-b').waitFor({ state: 'attached' })
  })
  await page.getByLabel('模型 1 名称').fill('model-a')
  await page.keyboard.press('Escape')
  await check('策略字段提供评估选项目录', async () => {
    await page.getByLabel('策略 1 名称').fill('chain')
    await catalogOption('chain_of_thought').waitFor({ state: 'attached' })
  })
  await check('目录外仍可手动输入', async () => {
    await page.getByLabel('策略 1 名称').fill('custom-strategy')
    assert.equal(
      await page.getByLabel('策略 1 名称').inputValue(),
      'custom-strategy',
    )
  })
  await page.getByLabel('策略 1 名称').fill('direct')
  await page.getByLabel('提交实验').click()
  await check('创建成功后导航到详情', async () => {
    await page.waitForURL('**/experiments/exp-fixture-new', { timeout: 5_000 })
    assert.ok(page.url().includes('/experiments/exp-fixture-new'))
  })
  await check('手动输入的模型与策略进入提交负载', () => {
    const body = report.experimentPost
    assert.ok(body, '未捕获到 POST /experiments 请求体')
    assert.equal(body.models?.[0]?.model, 'model-a')
    assert.equal(body.strategies?.[0]?.name, 'direct')
  })
  await page.screenshot({ path: resolve(outDir, 'create.png'), fullPage: true })
  report.screenshots.push('create.png')
}

async function listScenario(page) {
  await page.goto(`${base}/experiments`)
  await check('列表渲染实验行', async () => {
    await page.waitForSelector('table[aria-label="实验列表"]')
    assert.ok((await page.getByText('exp-fixture-1').count()) >= 1)
  })
  await check('状态筛选可见', async () =>
    assert.equal(await page.getByLabel('实验状态').count(), 1),
  )
  await page.screenshot({ path: resolve(outDir, 'list.png'), fullPage: true })
  report.screenshots.push('list.png')
}

async function detailScenario(page) {
  await page.goto(`${base}/experiments/exp-fixture-1`)
  await check('详情页渲染配置摘要', async () => {
    await page.waitForSelector('text=datasets/demo.json')
    assert.ok((await page.getByText('model-a').count()) >= 1)
  })
  await check('pending 实验提供启动按钮', async () => {
    assert.equal(await page.getByLabel('启动实验').count(), 1)
  })
  await page.screenshot({ path: resolve(outDir, 'detail.png'), fullPage: true })
  report.screenshots.push('detail.png')
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
  if (scenario === 'all' || scenario === 'create') await createScenario(page)
  if (scenario === 'all' || scenario === 'list') await listScenario(page)
  if (scenario === 'all' || scenario === 'detail') await detailScenario(page)
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
