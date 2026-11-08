/* global document, fetch, getComputedStyle, localStorage, setTimeout, URL, window */
// 直接加载视觉 smoke：针对生产构建直接打开工作流路由，确认共享工作流样式
// 已随入口 CSS 下发，且表格/面板的关键计算样式生效。运行方式见
// docs/frontend/QA.md。使用浏览器 fixture，不连接真实后端。
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import console from 'node:console'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const distEntry = resolve(frontendDir, 'dist/index.html')
const base = process.env.DIRECT_LOAD_BASE_URL || 'http://127.0.0.1:5191'
const outputDir = resolve(
  process.env.DIRECT_LOAD_QA_DIR ||
    resolve(frontendDir, '../docs/frontend/assets/direct-load'),
)
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const desktop = { width: 1440, height: 1000 }
const mobile = { width: 390, height: 844 }
const createdAt = '2026-11-03T00:00:00Z'

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
const experimentJob = {
  id: 'exp-fixture-1',
  name: '直接加载实验',
  status: 'pending',
  config: {
    name: '直接加载实验',
    dataset_path: 'datasets/demo.json',
    models: [{ model: 'model-a', temperature: 0.7 }],
    strategies: [{ name: 'direct' }],
    repeats: 1,
    budget: { max_calls: 10 },
    execution: 'serial',
    max_workers: 4,
  },
  error_message: null,
  created_at: createdAt,
  updated_at: createdAt,
}
const abTestJob = {
  id: 'ab-fixture-1',
  name: '直接加载 A/B',
  status: 'completed',
  task_id: null,
  config: {
    name: '直接加载 A/B',
    dataset_path: 'datasets/demo.json',
    model: { model: 'model-a' },
    strategy: { name: 'vanilla' },
    prompt_variants: [{ id: 'baseline' }, { id: 'treatment' }],
    seed: 42,
    max_workers: 4,
    api_key_id: 'key-fixture-1',
  },
  error_message: null,
  created_at: createdAt,
  updated_at: createdAt,
}
const suite = {
  id: 'suite-fixture-1',
  name: '直接加载套件',
  version: '1.0',
  description: null,
  frozen: false,
  problems: ['p1', 'p2'],
  created_at: createdAt,
  updated_at: createdAt,
}

const routes = [
  {
    name: 'experiments-list',
    path: '/experiments',
    waitFor: '.evaluation-list-table',
    table: true,
  },
  {
    name: 'experiments-create',
    path: '/experiments/new',
    waitFor: '.evaluation-panel',
    panel: true,
  },
  {
    name: 'experiment-detail',
    path: '/experiments/exp-fixture-1',
    waitFor: '.evaluation-panel',
    panel: true,
  },
  {
    name: 'abtests-list',
    path: '/ab-tests',
    waitFor: '.evaluation-list-table',
    table: true,
  },
  {
    name: 'abtests-create',
    path: '/ab-tests/new',
    waitFor: '.evaluation-panel',
    panel: true,
  },
  {
    name: 'benchmark-detail',
    path: '/benchmarks/suite-fixture-1',
    waitFor: '.evaluation-panel',
    panel: true,
  },
]

const report = {
  layer: 'browser-fixture (production build, direct load)',
  base,
  assertions: [],
  replaced: [],
  unknown: [],
  screenshots: [],
}

async function check(name, fn) {
  const record = { name, ok: false }
  report.assertions.push(record)
  try {
    await fn()
    record.ok = true
  } catch (error) {
    record.error = String(error)
  }
}

function mockRoute(context) {
  context.route('**/api/v1/**', (route, request) => {
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    // 生产构建使用同源 /api/v1；fulfill 仍带上 CORS 头，兼容被改指向已有服务。
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
    if (method === 'GET' && path === '/notifications')
      return reply({
        items: [],
        next_cursor: null,
        unread_count: 0,
        server_time: createdAt,
      })
    if (method === 'GET' && path === '/datasets') return reply([])
    if (method === 'GET' && path === '/api-keys') return reply(keys)
    if (method === 'GET' && path === '/evaluation-options')
      return reply({
        strategies: [{ name: 'direct' }, { name: 'chain_of_thought' }],
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
    if (method === 'GET' && path === '/tasks')
      return reply({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/experiments')
      return reply({
        items: [experimentJob],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/experiments/exp-fixture-1')
      return reply(experimentJob)
    if (method === 'GET' && path === '/ab-tests')
      return reply({
        items: [abTestJob],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/ab-tests/ab-fixture-1')
      return reply(abTestJob)
    if (method === 'GET' && path === '/benchmarks/suites')
      return reply({
        items: [suite],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (method === 'GET' && path === '/benchmarks/suites/suite-fixture-1')
      return reply(suite)
    if (method === 'GET' && path === '/benchmarks/suites/suite-fixture-1/runs')
      return reply({
        items: [],
        total: 0,
        limit: Number(url.searchParams.get('limit') || 20),
        offset: Number(url.searchParams.get('offset') || 0),
        has_more: false,
      })
    if (
      method === 'GET' &&
      path === '/benchmarks/learning-curve/suite-fixture-1'
    )
      return reply({
        suite_id: 'suite-fixture-1',
        suite_name: '直接加载套件',
        data: [],
        trends: { accuracy_growth_rate: null, cost_growth_rate: null },
      })
    report.unknown.push(`${method} ${path}`)
    return route.fulfill({
      status: 599,
      contentType: 'application/json',
      body: '{}',
    })
  })
}

async function waitForServer(url, child) {
  const deadline = Date.now() + 30_000
  let lastError
  while (Date.now() < deadline) {
    if (child?.exitCode !== null && child?.exitCode !== undefined)
      throw new Error(`Vite preview 提前退出，退出码 ${child.exitCode}`)
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch (error) {
      lastError = error
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250))
  }
  throw new Error(`Vite preview 未就绪：${lastError?.message ?? url}`)
}

async function collectSourceFiles(dir) {
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...(await collectSourceFiles(full)))
    else if (/\.(tsx?|jsx?)$/.test(entry.name)) files.push(full)
  }
  return files
}

async function assertEntryStylesheet() {
  const html = await readFile(distEntry, 'utf8')
  const hrefs = [...html.matchAll(/href="(\/assets\/[^"]+\.css)"/g)].map(
    (match) => match[1],
  )
  assert.ok(hrefs.length > 0, '入口 HTML 没有 <link rel="stylesheet">')
  const combined = (
    await Promise.all(
      hrefs.map((href) =>
        readFile(join(frontendDir, 'dist', href.replace(/^\//, '')), 'utf8'),
      ),
    )
  ).join('\n')
  for (const className of ['.evaluation-list-table', '.evaluation-panel']) {
    assert.ok(
      combined.includes(className),
      `入口 CSS 缺少共享规则 ${className}`,
    )
  }
  return hrefs
}

async function assertSingleImportSource() {
  const pagesDir = resolve(frontendDir, 'src/pages')
  const offenders = []
  for (const file of await collectSourceFiles(pagesDir)) {
    if ((await readFile(file, 'utf8')).includes('evaluations/workflow.css'))
      offenders.push(file.replace(`${frontendDir}/`, ''))
  }
  assert.deepEqual(
    offenders,
    [],
    `页面不应再导入 workflow.css：${offenders.join(', ')}`,
  )
}

function overflowOf(page) {
  return page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }))
}

async function assertNoOverflow(page, label) {
  const size = await overflowOf(page)
  assert.ok(
    size.document <= size.viewport && size.body <= size.viewport,
    `${label} 出现横向溢出：${JSON.stringify(size)}`,
  )
}

async function assertSharedCssSource(page) {
  const source = await page.evaluate(() => {
    for (const sheet of Array.from(document.styleSheets)) {
      let rules
      try {
        rules = sheet.cssRules
      } catch {
        continue
      }
      for (const rule of Array.from(rules)) {
        if (rule.selectorText?.includes('.evaluation-list-table')) {
          return {
            href: sheet.href,
            tag: sheet.ownerNode?.tagName ?? null,
            borderCollapse: rule.style.borderCollapse,
            minWidth: rule.style.minWidth,
          }
        }
      }
    }
    return null
  })
  assert.ok(source, '文档样式表缺少 .evaluation-list-table 规则')
  assert.equal(source.tag, 'LINK', '共享规则不是由入口 <link> 加载')
  assert.match(source.href ?? '', /\/assets\/index-[^/]+\.css$/)
  assert.equal(source.borderCollapse, 'collapse')
  assert.equal(source.minWidth, '760px')
}

async function assertTableStyles(page) {
  const styles = await page
    .locator('.evaluation-list-table')
    .first()
    .evaluate((element) => {
      const table = getComputedStyle(element)
      const cell = element.querySelector('td, th')
      const cellStyle = cell ? getComputedStyle(cell) : null
      return {
        borderCollapse: table.borderCollapse,
        minWidth: table.minWidth,
        paddingTop: cellStyle?.paddingTop ?? null,
        paddingLeft: cellStyle?.paddingLeft ?? null,
      }
    })
  assert.equal(styles.borderCollapse, 'collapse')
  assert.equal(styles.minWidth, '760px')
  assert.equal(styles.paddingTop, '16px')
  assert.equal(styles.paddingLeft, '12px')
}

async function assertPanelStyles(page, expectedPadding) {
  const styles = await page
    .locator('.evaluation-panel')
    .first()
    .evaluate((element) => getComputedStyle(element).padding)
  assert.equal(styles, expectedPadding)
}

async function assertWorkflowContainer(page) {
  const minWidth = await page
    .locator('.evaluation-workflow')
    .first()
    .evaluate((element) => getComputedStyle(element).minWidth)
  assert.equal(minWidth, '0px')
}

async function visit(browser, spec, viewport) {
  const context = await browser.newContext({
    viewport,
    reducedMotion: 'reduce',
  })
  await context.addInitScript(() => {
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'direct-load-fixture',
        username: 'direct-load-fixture',
        expiresAt: Date.now() + 3_600_000,
      }),
    )
  })
  mockRoute(context)
  const page = await context.newPage()
  const errors = []
  const failed = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('response', (response) => {
    if (response.status() >= 400)
      failed.push(`${response.status()} ${response.url()}`)
  })
  const suffix = viewport === mobile ? '-mobile' : ''
  const label = `${spec.name}${suffix}`
  const unknownStart = report.unknown.length
  await page.goto(`${base}${spec.path}`)
  await check(`${label} 直接加载后渲染`, async () => {
    await page.locator(spec.waitFor).first().waitFor({ timeout: 15_000 })
  })
  await check(`${label} 共享样式来自入口 CSS`, () =>
    assertSharedCssSource(page),
  )
  await check(`${label} 工作流容器 min-width`, () =>
    assertWorkflowContainer(page),
  )
  if (spec.table)
    await check(`${label} 表格关键样式`, () => assertTableStyles(page))
  if (spec.panel)
    await check(`${label} 面板内边距`, () =>
      assertPanelStyles(page, viewport === mobile ? '16px' : '24px'),
    )
  await check(`${label} 无横向溢出`, () => assertNoOverflow(page, label))
  await check(`${label} 无页面异常`, () =>
    assert.deepEqual(errors, [], `pageerror: ${errors.join(' | ')}`),
  )
  await check(`${label} 无未声明请求`, () => {
    const unknown = report.unknown.slice(unknownStart)
    assert.deepEqual(unknown, [], `未声明：${unknown.join(', ')}`)
  })
  await check(`${label} 无失败响应`, () =>
    assert.deepEqual(failed, [], `失败响应：${failed.join(' | ')}`),
  )
  const screenshot = `${label}.png`
  await page.screenshot({
    path: resolve(outputDir, screenshot),
    fullPage: true,
  })
  report.screenshots.push(screenshot)
  await context.close()
}

let server
let browser
let ownsServer = false
try {
  await mkdir(outputDir, { recursive: true })
  const distExists = await readFile(distEntry, 'utf8').then(
    () => true,
    () => false,
  )
  assert.ok(
    distExists,
    '缺少构建产物 dist/index.html：请先在 frontend 运行 npm run build',
  )

  await check('入口 CSS 包含共享工作流规则', () => assertEntryStylesheet())
  await check('workflow.css 只有共享布局一个导入来源', () =>
    assertSingleImportSource(),
  )

  if (process.env.DIRECT_LOAD_BASE_URL) {
    await waitForServer(`${base}/`)
  } else {
    const port = new URL(base).port || '5191'
    server = spawn(
      process.execPath,
      [
        resolve(frontendDir, 'node_modules/vite/bin/vite.js'),
        'preview',
        '--host',
        '127.0.0.1',
        '--port',
        port,
        '--strictPort',
      ],
      {
        cwd: frontendDir,
        detached: process.platform !== 'win32',
        stdio: 'ignore',
      },
    )
    ownsServer = true
    await waitForServer(`${base}/`, server)
  }

  browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {}),
  })

  for (const spec of routes) {
    await visit(browser, spec, desktop)
  }
  await visit(browser, routes[0], mobile)
  await visit(browser, routes[1], mobile)
} finally {
  if (browser) await browser.close()
  if (ownsServer && server?.pid) {
    if (process.platform === 'win32') server.kill('SIGTERM')
    else process.kill(-server.pid, 'SIGTERM')
  }
  await mkdir(outputDir, { recursive: true })
  await writeFile(
    resolve(outputDir, 'report.json'),
    JSON.stringify(report, null, 2),
  )
  const failed = report.assertions.filter((item) => !item.ok)
  console.log(
    `direct-load assertions=${report.assertions.length} failed=${failed.length} unknown=${report.unknown.length}`,
  )
  for (const item of failed) console.log(`FAIL ${item.name}: ${item.error}`)
  if (failed.length) process.exitCode = 1
}
