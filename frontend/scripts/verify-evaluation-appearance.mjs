/* global console, document, fetch, HTMLElement, localStorage, setTimeout, URL, window */
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoRoot = resolve(frontendDir, '..')
const base =
  process.env.EVALUATION_APPEARANCE_BASE_URL || 'http://127.0.0.1:5189'
const outputDir = resolve(
  process.env.EVALUATION_APPEARANCE_QA_DIR ||
    resolve(repoRoot, 'docs/frontend/assets/evaluations/appearance'),
)
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const variants = ['orbit', 'precision', 'studio']
const themes = ['light', 'dark']
const widths = [320, 390, 768, 1440]
const createdAt = '2026-10-26T00:00:00Z'
const evaluationId = 'appearance-evaluation'
const task = {
  evaluation_id: evaluationId,
  created_at: createdAt,
  updated_at: createdAt,
  status: 'completed',
  can_start: false,
  can_cancel: false,
  execution_progress: { completed_units: 1, total_units: 1, percentage: 100 },
  strategy_names: ['direct'],
  model: 'model-a',
  problem_count: 1,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
}
const keys = [
  {
    id: 'appearance-key',
    key_name: '布局验收密钥',
    provider: 'openai',
    created_at: 1792533600,
    last_used_at: null,
    verified: true,
    usage_count: 0,
    masked_preview: null,
  },
]
const problem = {
  problem_id: 'appearance-problem',
  title: '布局验收题目',
  difficulty: 'easy',
  source: 'shared',
}
const problems = Array.from({ length: 21 }, (_, index) => ({
  ...problem,
  problem_id: index === 0 ? problem.problem_id : `appearance-problem-${index}`,
}))
const resultSummary = {
  id: evaluationId,
  run_id: null,
  status: 'completed',
  model: 'model-a',
  strategy_names: ['direct'],
  created_at: createdAt,
  completed_at: createdAt,
}
const resultDetail = {
  run_id: null,
  status: 'completed',
  created_at: createdAt,
  completed_at: createdAt,
  strategies: [
    {
      name: 'direct',
      success_rate: 1,
      total_problems: 1,
      solved_problems: 1,
      avg_tokens: 1,
      estimated_cost_usd: 0,
      unknown_cost_count: 0,
      avg_execution_time: 0.01,
      by_difficulty: {
        easy: { success_rate: 1, solved: 1, total: 1 },
      },
    },
  ],
  problems: {
    items: [
      {
        problem_id: problem.problem_id,
        strategy: 'direct',
        status: 'success',
        iterations: 1,
        tokens: 1,
        execution_time: 0.01,
      },
    ],
    total: 1,
    limit: 20,
    offset: 0,
    has_more: false,
  },
}
const report = {
  scenario: 'appearance',
  layer:
    'Chromium browser fixture; HTTP identity and business responses replaced',
  source: {
    head: execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: repoRoot,
      encoding: 'utf8',
    }).trim(),
    dirty: execFileSync('git', ['status', '--short'], {
      cwd: repoRoot,
      encoding: 'utf8',
    }).trim(),
  },
  matrix: { variants, themes, widths },
  routes: [
    '/evaluations/new',
    '/evaluations',
    `/evaluations/${evaluationId}`,
    '/results',
    `/results/${evaluationId}`,
  ],
  replaced: [
    'HTTP /api/v1/users/me and /api/v1/api-keys',
    'HTTP evaluation options, creation, list and detail responses',
    'HTTP results list and detail responses',
    'localStorage test session; no credentials or provider calls',
  ],
  limitations: [
    'Chromium viewport simulation only; no physical iOS/Android device testing.',
    'No Safari/Firefox, screen reader, real backend, Redis/Celery, sandbox or model-provider validation.',
    'HTTP fixtures prove frontend interactions and payloads, not successful real-backend execution.',
  ],
  assertions: [],
  requests: [],
  screenshots: [],
  unknownRequests: [],
}
let activePage
let activeCombination

function record(name, run) {
  const context = {
    combination: activeCombination,
    page: new URL(activePage.url()).pathname,
  }
  return Promise.resolve()
    .then(run)
    .then(() => report.assertions.push({ name, ...context, pass: true }))
    .catch((error) => {
      report.assertions.push({
        name,
        ...context,
        pass: false,
        message: error.message,
      })
      throw error
    })
}

async function choose(page, label, text) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page
    .locator('.ant-select-dropdown:visible .ant-select-item-option')
    .filter({ hasText: new RegExp(`^${text}$`) })
    .click()
  await page.keyboard.press('Escape')
}

async function switchAppearance(page, variant, theme) {
  const otherVariant = variant === 'orbit' ? 'precision' : 'orbit'
  const otherTheme = theme === 'light' ? 'dark' : 'light'
  const style = page.getByLabel('选择页面风格', { exact: true })
  const color = page.getByLabel('主题偏好', { exact: true })
  await style.selectOption(otherVariant)
  await color.selectOption(otherTheme)
  await style.selectOption(variant)
  await color.selectOption(theme)
  await page.waitForFunction(
    ({ expectedVariant, expectedTheme }) => {
      const state = JSON.parse(localStorage.getItem('llm-harness-ui') || 'null')
      return (
        document.documentElement.dataset.theme === expectedTheme &&
        document.documentElement.dataset.design === expectedVariant &&
        state?.appearanceVariant === expectedVariant &&
        state?.themes?.[expectedVariant] === expectedTheme
      )
    },
    { expectedVariant: variant, expectedTheme: theme },
  )
}

async function assertNoPageOverflow(page, label) {
  const size = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }))
  assert.ok(
    size.document <= size.viewport && size.body <= size.viewport,
    `${label}: ${JSON.stringify(size)}`,
  )
}

async function assertKeyboardReachable(page, locator, label) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur()
  })
  for (let index = 0; index < 80; index += 1) {
    await page.keyboard.press('Tab')
    if (
      await locator.evaluate(
        (element) =>
          element === document.activeElement ||
          element.contains(document.activeElement),
      )
    )
      return
  }
  throw new Error(`${label} 未出现在键盘 Tab 顺序中`)
}

async function waitForServer(url, child) {
  const deadline = Date.now() + 30_000
  let lastError
  while (Date.now() < deadline) {
    if (child?.exitCode !== null && child?.exitCode !== undefined)
      throw new Error(`Vite exited early with code ${child.exitCode}`)
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`Vite did not become ready: ${lastError?.message ?? url}`)
}

let server
let ownsServer = false
let browser
try {
  await mkdir(outputDir, { recursive: true })
  if (process.env.EVALUATION_APPEARANCE_BASE_URL) {
    await waitForServer(`${base}/`)
  } else {
    const port = new URL(base).port || '5189'
    server = spawn(
      process.execPath,
      [
        resolve(frontendDir, 'node_modules/vite/bin/vite.js'),
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

  for (const variant of variants) {
    for (const theme of themes) {
      for (const width of widths) {
        const combo = `${variant}/${theme}/${width}px`
        const context = await browser.newContext({
          viewport: { width, height: 1000 },
          reducedMotion: 'reduce',
        })
        const page = await context.newPage()
        activePage = page
        activeCombination = { variant, theme, width }
        const calls = []
        const errors = []
        page.on('pageerror', (error) => errors.push(error.message))
        await context.addInitScript(
          ({ selectedVariant, selectedTheme }) => {
            localStorage.setItem(
              'llm-harness-session',
              JSON.stringify({
                marker: 'appearance-fixture',
                username: 'appearance-fixture',
                expiresAt: Date.now() + 3_600_000,
              }),
            )
            localStorage.setItem(
              'llm-harness-ui',
              JSON.stringify({
                appearanceVariant: selectedVariant,
                themes: {
                  orbit: selectedTheme,
                  precision: selectedTheme,
                  studio: selectedTheme,
                },
                sidebarCollapsed: false,
              }),
            )
          },
          { selectedVariant: variant, selectedTheme: theme },
        )
        await context.route('**/api/v1/**', async (route) => {
          const request = route.request()
          const url = new URL(request.url())
          const path = url.pathname.replace('/api/v1', '')
          const method = request.method()
          const call = {
            combo,
            at: Date.now(),
            path,
            method,
            query: url.search,
            ...(request.postData() ? { payload: request.postDataJSON() } : {}),
          }
          calls.push(call)
          report.requests.push(call)
          const headers = {
            'access-control-allow-origin': base,
            'access-control-allow-credentials': 'true',
          }
          const send = (data, status = 200) =>
            route.fulfill({ status, headers, json: { data } })
          if (method === 'OPTIONS')
            return route.fulfill({
              status: 204,
              headers: {
                ...headers,
                'access-control-allow-methods': 'GET,POST',
                'access-control-allow-headers': 'content-type,x-csrf-token',
              },
            })
          if (method === 'GET' && path === '/users/me')
            return send({
              username: 'appearance-fixture',
              role: 'user',
              email: 'appearance@example.invalid',
              created_at: '2026-10-26',
            })
          if (method === 'GET' && path === '/api-keys') return send(keys)
          if (method === 'GET' && path === '/evaluation-options')
            return send({
              strategies: [{ name: 'direct' }],
              sources: [{ id: 'shared', label: '共享题目', problem_count: 21 }],
            })
          if (method === 'GET' && path === '/evaluation-options/models')
            return send({
              provider: 'openai',
              models: ['model-a'],
              complete: true,
            })
          if (method === 'GET' && path === '/evaluation-options/problems') {
            const offset = Number(url.searchParams.get('offset') ?? 0)
            const limit = Number(url.searchParams.get('limit') ?? 20)
            return send({
              items: problems.slice(offset, offset + limit),
              total: problems.length,
              offset,
              limit,
              has_more: offset + limit < problems.length,
            })
          }
          if (method === 'POST' && path === '/evaluations')
            return send(task, 201)
          if (
            method === 'POST' &&
            path === `/evaluations/${evaluationId}/start`
          )
            return send(task)
          if (method === 'GET' && path === '/evaluations') {
            const status = url.searchParams.get('status')
            const items = Array.from({ length: 21 }, (_, index) => ({
              ...task,
              evaluation_id: index === 0 ? evaluationId : `appearance-${index}`,
            })).filter((item) => !status || item.status === status)
            const limit = Number(url.searchParams.get('limit') ?? 20)
            const offset = Number(url.searchParams.get('offset') ?? 0)
            return send({
              items: items.slice(offset, offset + limit),
              total: items.length,
              limit,
              offset,
              has_more: offset + limit < items.length,
            })
          }
          if (method === 'GET' && path.startsWith('/evaluations/'))
            return send(task)
          if (method === 'GET' && path === '/results') {
            const status = url.searchParams.get('status')
            const items = status === 'failed' ? [] : [resultSummary]
            const limit = Number(url.searchParams.get('limit') ?? 20)
            const offset = Number(url.searchParams.get('offset') ?? 0)
            return send({
              items: items.slice(offset, offset + limit),
              total: items.length,
              limit,
              offset,
              has_more: offset + limit < items.length,
            })
          }
          if (method === 'GET' && path === `/results/${evaluationId}`)
            return send(resultDetail)
          report.unknownRequests.push(call)
          return route.fulfill({
            status: 501,
            headers,
            json: { message: `未声明的外观 fixture 请求: ${method} ${path}` },
          })
        })

        await page.goto(`${base}/evaluations/new`)
        await page
          .getByRole('heading', { name: '创建评估', exact: true })
          .waitFor()
        await choose(page, 'API 密钥', '布局验收密钥 · openai')
        await choose(page, '模型', 'model-a')
        await choose(page, '策略', 'direct')
        await page
          .getByRole('checkbox', {
            name: '选择题目 appearance-problem',
            exact: true,
          })
          .check()
        await page
          .getByLabel('预算上限（USD，可选）', { exact: true })
          .fill('0.25')
        await page
          .getByRole('button', { name: '下一页题目', exact: true })
          .click()
        const secondProblem = page.getByRole('checkbox', {
          name: '选择题目 appearance-problem-20',
          exact: true,
        })
        await secondProblem.check()
        await switchAppearance(page, variant, theme)
        await record(`${combo} 创建草稿、选择与键盘操作保留`, async () => {
          assert.equal(await secondProblem.isChecked(), true)
          await page.getByText('已选 2 道题目', { exact: true }).waitFor()
          for (const [label, selected] of [
            ['API 密钥', '布局验收密钥 · openai'],
            ['模型', 'model-a'],
            ['策略', 'direct'],
          ]) {
            assert.ok(
              (
                await page
                  .getByRole('combobox', { name: label, exact: true })
                  .locator(
                    'xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " ant-select ")][1]',
                  )
                  .textContent()
              ).includes(selected),
              `${combo} ${label} 保留`,
            )
          }
          await page
            .getByRole('button', { name: '上一页题目', exact: true })
            .click()
          await page
            .getByRole('checkbox', {
              name: '选择题目 appearance-problem',
              exact: true,
            })
            .waitFor()
          assert.equal(
            await page.getByLabel('预算上限（USD，可选）').inputValue(),
            '0.25',
          )
          assert.equal(
            await page
              .getByRole('checkbox', {
                name: '选择题目 appearance-problem',
                exact: true,
              })
              .isChecked(),
            true,
          )
          await assertNoPageOverflow(page, `${combo} create`)
          await assertKeyboardReachable(
            page,
            page.getByRole('button', { name: '创建并启动', exact: true }),
            `${combo} 创建并启动`,
          )
        })
        if (variant === 'orbit' && theme === 'light' && width === 320) {
          const file = 'create-orbit-light-320.png'
          await page.evaluate(() => window.scrollTo(0, 0))
          await page.screenshot({
            path: resolve(outputDir, file),
            fullPage: true,
          })
          report.screenshots.push(file)
        }
        await page
          .getByRole('button', { name: '创建并启动', exact: true })
          .click()
        await page
          .getByRole('heading', { name: '评估任务详情', exact: true })
          .waitFor({ timeout: 5000 })
        await page.getByText('已完成', { exact: true }).first().waitFor()
        await record(`${combo} 创建及启动请求保留完整跨页配置`, () => {
          const creates = calls.filter(
            (call) => call.method === 'POST' && call.path === '/evaluations',
          )
          assert.equal(creates.length, 1)
          assert.deepEqual(creates[0].payload, {
            api_key_id: 'appearance-key',
            model: 'model-a',
            strategy_names: ['direct'],
            problem_ids: ['appearance-problem', 'appearance-problem-20'],
            budget_cap_usd: 0.25,
          })
          assert.equal(
            calls.filter(
              (call) =>
                call.method === 'POST' &&
                call.path === `/evaluations/${evaluationId}/start`,
            ).length,
            1,
          )
        })

        await page.goto(`${base}/evaluations?limit=20&offset=0`)
        await page
          .getByRole('table', { name: '评估任务列表', exact: true })
          .waitFor()
        const filteredTaskResponse = page.waitForResponse((response) => {
          const url = new URL(response.url())
          return (
            url.pathname === '/api/v1/evaluations' &&
            url.searchParams.get('status') === 'completed'
          )
        })
        await choose(page, '任务状态', '已完成')
        await filteredTaskResponse
        await page
          .getByRole('table', { name: '评估任务列表', exact: true })
          .waitFor()
        const taskQuery = new URL(page.url()).searchParams
        assert.equal(taskQuery.get('status'), 'completed')
        const taskListCalls = calls.filter(
          (call) => call.path === '/evaluations',
        ).length
        const taskUrl = page.url()
        await switchAppearance(page, variant, theme)
        await record(`${combo} 任务筛选、URL 与键盘入口保留`, async () => {
          assert.equal(page.url(), taskUrl)
          assert.equal(
            await page
              .getByRole('combobox', { name: '任务状态', exact: true })
              .evaluate((element) =>
                element.closest('.ant-select').textContent.trim(),
              ),
            '已完成',
          )
          assert.equal(
            new URL(page.url()).searchParams.get('status'),
            'completed',
          )
          assert.equal(
            calls.filter((call) => call.path === '/evaluations').length,
            taskListCalls,
          )
          await assertNoPageOverflow(page, `${combo} task list`)
          await assertKeyboardReachable(
            page,
            page.getByRole('region', {
              name: '可滚动的评估任务列表',
              exact: true,
            }),
            `${combo} 任务列表滚动区域`,
          )
        })
        if (variant === 'precision' && theme === 'dark' && width === 390) {
          const file = 'task-list-precision-dark-390.png'
          await page.evaluate(() => window.scrollTo(0, 0))
          await page.screenshot({
            path: resolve(outputDir, file),
            fullPage: true,
          })
          report.screenshots.push(file)
        }
        await page
          .getByRole('link', { name: evaluationId, exact: true })
          .click()
        await page
          .getByRole('heading', { name: '评估任务详情', exact: true })
          .waitFor()
        await record(`${combo} 任务详情入口与键盘可操作`, async () => {
          assert.ok(new URL(page.url()).pathname.endsWith(evaluationId))
          await assertNoPageOverflow(page, `${combo} task detail`)
          await assertKeyboardReachable(
            page,
            page.getByRole('button', { name: '刷新任务', exact: true }),
            `${combo} 刷新任务`,
          )
        })
        if (variant === 'studio' && theme === 'light' && width === 768) {
          const file = 'task-detail-studio-light-768.png'
          await page.evaluate(() => window.scrollTo(0, 0))
          await page.screenshot({
            path: resolve(outputDir, file),
            fullPage: true,
          })
          report.screenshots.push(file)
        }

        await page.goto(`${base}/results?limit=20&offset=0`)
        await page
          .getByRole('table', { name: '评估结果列表', exact: true })
          .waitFor()
        const filteredResultResponse = page.waitForResponse((response) => {
          const url = new URL(response.url())
          return (
            url.pathname === '/api/v1/results' &&
            url.searchParams.get('status') === 'completed'
          )
        })
        await choose(page, '结果状态', '已完成')
        await filteredResultResponse
        await page
          .getByRole('table', { name: '评估结果列表', exact: true })
          .waitFor()
        const resultListCalls = calls.filter(
          (call) => call.path === '/results',
        ).length
        const resultUrl = page.url()
        await switchAppearance(page, variant, theme)
        await record(`${combo} 结果筛选、URL 与键盘入口保留`, async () => {
          assert.equal(page.url(), resultUrl)
          assert.equal(
            await page
              .getByRole('combobox', { name: '结果状态', exact: true })
              .evaluate((element) =>
                element.closest('.ant-select').textContent.trim(),
              ),
            '已完成',
          )
          assert.equal(
            new URL(page.url()).searchParams.get('status'),
            'completed',
          )
          assert.equal(
            calls.filter((call) => call.path === '/results').length,
            resultListCalls,
          )
          await assertNoPageOverflow(page, `${combo} result list`)
          await assertKeyboardReachable(
            page,
            page.getByRole('region', {
              name: '可滚动的评估结果列表',
              exact: true,
            }),
            `${combo} 结果列表滚动区域`,
          )
        })
        await page
          .getByRole('link', { name: evaluationId, exact: true })
          .click()
        await page
          .getByRole('heading', { name: '评估结果详情', exact: true })
          .waitFor()
        await page
          .getByRole('table', { name: '单题结果', exact: true })
          .waitFor()
        await record(
          `${combo} 结果详情与横向滚动表格可由键盘访问`,
          async () => {
            assert.ok(new URL(page.url()).pathname.endsWith(evaluationId))
            await assertNoPageOverflow(page, `${combo} result detail`)
            await assertKeyboardReachable(
              page,
              page.getByRole('region', {
                name: '可滚动的单题结果',
                exact: true,
              }),
              `${combo} 单题结果滚动区域`,
            )
          },
        )
        if (variant === 'studio' && theme === 'dark' && width === 1440) {
          const file = 'result-detail-studio-dark-1440.png'
          await page.evaluate(() => window.scrollTo(0, 0))
          await page.screenshot({
            path: resolve(outputDir, file),
            fullPage: true,
          })
          report.screenshots.push(file)
        }
        await record(`${combo} 通知抽屉 Esc 关闭并恢复焦点`, async () => {
          const trigger = page.getByRole('button', { name: /^通知中心，/ })
          await assertKeyboardReachable(page, trigger, `${combo} 通知按钮`)
          await page.keyboard.press('Enter')
          await page
            .locator('.notification-drawer')
            .waitFor({ state: 'visible' })
          await page.waitForFunction(
            () =>
              !!document.activeElement
                ?.closest('.ant-drawer')
                ?.querySelector('.notification-drawer'),
          )
          await page.keyboard.press('Escape')
          await page
            .locator('.notification-drawer')
            .waitFor({ state: 'hidden' })
          await page.waitForFunction(() =>
            document.activeElement
              ?.getAttribute('aria-label')
              ?.startsWith('通知中心，'),
          )
          assert.equal(await trigger.getAttribute('aria-expanded'), 'false')
        })
        if (width <= 1023) {
          await record(`${combo} 移动菜单 Esc 关闭并恢复焦点`, async () => {
            const menu = page.getByRole('button', {
              name: '打开导航菜单',
              exact: true,
            })
            await assertKeyboardReachable(page, menu, `${combo} 移动导航按钮`)
            await page.keyboard.press('Enter')
            await page
              .locator('.navigation-drawer')
              .waitFor({ state: 'visible' })
            assert.equal(await menu.getAttribute('aria-expanded'), 'true')
            await page.waitForFunction(
              () =>
                !!document.activeElement
                  ?.closest('.ant-drawer')
                  ?.querySelector('.navigation-drawer'),
            )
            await page.keyboard.press('Escape')
            await page
              .locator('.navigation-drawer')
              .waitFor({ state: 'hidden' })
            await page.waitForFunction(
              () =>
                document.activeElement?.getAttribute('aria-label') ===
                '打开导航菜单',
            )
            assert.equal(await menu.getAttribute('aria-expanded'), 'false')
          })
          await record(`${combo} 移动抽屉创建入口可用`, async () => {
            await page
              .getByRole('button', { name: '打开导航菜单', exact: true })
              .click()
            await page
              .locator('.navigation-drawer')
              .getByRole('button', { name: '创建评估', exact: true })
              .click()
            await page
              .getByRole('heading', { name: '创建评估', exact: true })
              .waitFor()
            await page
              .locator('.navigation-drawer')
              .waitFor({ state: 'hidden' })
          })
        }
        if (width <= 767) {
          await record(`${combo} 底部导航可由键盘进入结果页`, async () => {
            const bottom = page.getByRole('navigation', {
              name: '常用页面',
              exact: true,
            })
            const resultsLink = bottom.getByRole('link', {
              name: '结果',
              exact: true,
            })
            await assertKeyboardReachable(
              page,
              resultsLink,
              `${combo} 底部结果入口`,
            )
            await page.keyboard.press('Enter')
            await page
              .getByRole('heading', { name: '评估结果', exact: true })
              .waitFor()
            assert.equal(new URL(page.url()).pathname, '/results')
            await assertNoPageOverflow(page, `${combo} mobile navigation`)
          })
        }
        assert.deepEqual(errors, [], `${combo} browser errors`)
        await context.close()
      }
    }
  }
  assert.deepEqual(report.unknownRequests, [], 'No undeclared API requests')
  assert.ok(report.assertions.every((item) => item.pass))
  report.pass = true
} catch (error) {
  report.pass = false
  report.failure = { message: error.message, stack: error.stack }
  if (activePage && !activePage.isClosed()) {
    report.failure.url = activePage.url()
    report.failure.activeElement = await activePage.evaluate(
      () => document.activeElement?.outerHTML,
    )
  }
  console.error(error)
  process.exitCode = 1
} finally {
  if (browser) await browser.close()
  await writeFile(
    resolve(outputDir, 'appearance.json'),
    JSON.stringify(report, null, 2),
  )
  console.log(
    JSON.stringify({
      scenario: 'appearance',
      pass: report.pass,
      assertions: report.assertions.filter((item) => item.pass).length,
      failed: report.assertions.filter((item) => !item.pass).length,
      outputDir,
      report: resolve(outputDir, 'appearance.json'),
      screenshots: report.screenshots,
    }),
  )
  if (ownsServer && server?.pid) {
    try {
      if (process.platform === 'win32') server.kill('SIGTERM')
      else process.kill(-server.pid, 'SIGTERM')
    } catch {
      /* The owned Vite process already exited. */
    }
  }
}
