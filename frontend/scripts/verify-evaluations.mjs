/* global document, localStorage, window, fetch, setTimeout, getComputedStyle */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
import { recordCheck } from './fixture-checks.mjs'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.EVALUATION_BASE_URL || 'http://127.0.0.1:5180'
const out = resolve(
  process.env.EVALUATION_QA_DIR ||
    '../docs/superpowers/reports/assets/evaluation-live-workflow/fixture',
)
const scenarioIndex = process.argv.indexOf('--scenario')
const scenario = scenarioIndex === -1 ? 'all' : process.argv[scenarioIndex + 1]
const known = [
  'create',
  'list',
  'detail',
  'progress',
  'results',
  'states',
  'entries',
  'appearance',
  'security',
  'all',
]
assert.ok(known.includes(scenario), `Unknown scenario: ${scenario}`)
await mkdir(out, { recursive: true })
const report = {
  scenario,
  source: {
    head: execFileSync('git', ['rev-parse', 'HEAD'], {
      encoding: 'utf8',
    }).trim(),
    dirty: execFileSync('git', ['status', '--short'], {
      encoding: 'utf8',
    }).trim(),
  },
  layer: 'browser-fixture (not backend E2E)',
  assertions: [],
  requests: [],
  unknown: [],
  screenshots: [],
  replaced: [
    'WebSocket progress: in-memory fixture (no real upstream connection)',
    'HTTP /api/v1/users/me',
    'HTTP /api/v1/api-keys',
    'HTTP /api/v1/evaluation-options and children',
    'HTTP /api/v1/evaluations create/start/get',
    'results scenario: HTTP /api/v1/results list/detail',
    'localStorage session marker (no credentials)',
    'security only: isolated HTML and in-memory auth/HTTP transport',
  ],
  real: [
    'React StrictMode',
    'router',
    'session provider',
    'creation store',
    'evaluation client',
  ],
}
function check(name, fn) {
  return recordCheck(report.assertions, name, fn)
}
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
})
const evaluation = {
  evaluation_id: 'eval-fixture-1',
  created_at: '2026-10-21T10:00:00Z',
  updated_at: '2026-10-21T10:00:00Z',
  status: 'pending',
  can_start: true,
  can_cancel: true,
  execution_progress: { completed_units: 0, total_units: 2, percentage: 0 },
  strategy_names: ['direct'],
  model: 'model-a',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
}
const keys = ['a', 'b', 'slow'].map((id) => ({
  id: `key-${id}`,
  key_name: `密钥 ${id.toUpperCase()}`,
  provider: 'openai',
  created_at: 1792533600,
  last_used_at: null,
  verified: true,
  usage_count: 0,
  masked_preview: null,
}))
async function fixture(mode = 'start-error', entry = '/evaluations/new') {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  const errors = []
  const calls = []
  let detail = { ...evaluation }
  let progressPercentage = 20
  let advanceProgress = () => {
    throw new Error('Progress socket is not subscribed')
  }
  let denyProgress = () => {
    throw new Error('Progress socket is not connected')
  }
  const detailIntervals = []
  const detailProgress = []
  let subscriptionAt = 0
  let wsUrls = []
  let starts = 0
  let detailFailure = 0
  let resultFailure = 0
  let resultsListFailure = false
  const resultIntervals = []
  let heldResultOffset = null
  let resultGate = null
  let releaseResult = () => {}
  let resultHeld = Promise.resolve()
  let markResultHeld = () => {}
  let detailGate = null
  let releaseDetail = () => {}
  let releaseList
  let releaseStale
  let failList = mode === 'list-error'
  const listGate = new Promise((resolve) => {
    releaseList = resolve
  })
  const staleGate = new Promise((resolve) => {
    releaseStale = resolve
  })
  page.on('pageerror', (e) => errors.push(e.message))
  await context.addInitScript(() =>
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'evaluation-fixture',
        username: 'browser-fixture',
        expiresAt: Date.now() + 3600000,
      }),
    ),
  )
  await context.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = req.method()
    const call = {
      path,
      method,
      query: url.search,
      ...(req.postData() ? { payload: req.postDataJSON() } : {}),
    }
    calls.push(call)
    report.requests.push({ mode, ...call })
    const headers = {
      'access-control-allow-origin': base,
      'access-control-allow-credentials': 'true',
    }
    const send = (data, status = 200) =>
      route.fulfill({ status, headers, json: { data } })
    if (mode.startsWith('results') && method === 'GET') {
      if (path === '/results') {
        if (resultsListFailure)
          return route.fulfill({
            status: 503,
            headers,
            json: { message: '结果列表暂不可用' },
          })
        const limit = Number(url.searchParams.get('limit'))
        const offset = Number(url.searchParams.get('offset'))
        let items = Array.from({ length: 21 }, (_, i) => ({
          id: i === 0 ? 'eval-fixture-1' : `eval-result-${i + 1}`,
          run_id: i === 0 ? null : `run-${i + 1}`,
          status: i === 1 ? 'future-result' : i % 2 ? 'failed' : 'completed',
          model: 'result-model',
          strategy_names: ['direct', 'cot'],
          created_at: evaluation.created_at,
          completed_at: i === 0 ? null : evaluation.updated_at,
        }))
        if (mode === 'results-empty') items = []
        const status = url.searchParams.get('status')
        if (status) items = items.filter((item) => item.status === status)
        return send({
          items: items.slice(offset, offset + limit),
          total: items.length,
          limit,
          offset,
          has_more: offset + limit < items.length,
        })
      }
      if (path.startsWith('/results/')) {
        if (
          Number(url.searchParams.get('offset')) === heldResultOffset &&
          resultGate
        ) {
          markResultHeld()
          await resultGate
        }
        const started = Date.now()
        await new Promise((resolve) => setTimeout(resolve, 180))
        if (resultFailure)
          return route.fulfill({
            status: resultFailure,
            headers,
            json: { message: '结果读取失败' },
          })
        const limit = Number(url.searchParams.get('limit'))
        const offset = Number(url.searchParams.get('offset'))
        const units = Array.from({ length: 24 }, (_, i) => ({
          problem_id: `result-problem-${Math.floor(i / 2) + 1}`,
          strategy: i % 2 ? 'cot' : 'direct',
          status: i === 2 ? 'timeout' : i === 3 ? 'future-unit' : 'success',
          iterations: i === 0 ? null : 0,
          tokens: i === 0 ? null : 0,
          execution_time: i === 0 ? null : 1.25,
        }))
        const response = await send({
          run_id: null,
          status: mode === 'results-live' ? 'running' : 'completed',
          created_at: evaluation.created_at,
          completed_at: null,
          strategies: ['direct', 'cot'].map((name, i) => ({
            name,
            success_rate: i ? 0.75 : 0.5,
            total_problems: 12,
            solved_problems: i ? 9 : 6,
            avg_tokens:
              mode === 'results-live' && progressPercentage > 20 ? 300 : 100,
            estimated_cost_usd: i ? 0.12 : 0,
            unknown_cost_count: i ? 1 : 2,
            avg_execution_time: 1.25,
            by_difficulty: { easy: { success_rate: 0.5, solved: 2, total: 4 } },
          })),
          problems: {
            items: units.slice(offset, offset + limit),
            total: units.length,
            limit,
            offset,
            has_more: offset + limit < units.length,
          },
        })
        resultIntervals.push([started, Date.now()])
        return response
      }
      if (path === '/evaluations/eval-fixture-1' && detailFailure)
        return route.fulfill({
          status: detailFailure,
          headers,
          json: { message: '任务不可访问' },
        })
      if (path === '/evaluations/eval-fixture-1' && mode !== 'results-live')
        return send({
          ...evaluation,
          status: 'completed',
          can_start: false,
          can_cancel: false,
        })
    }
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
        username: 'browser-fixture',
        role: 'user',
        email: 'fixture@example.com',
        created_at: '2026-10-21',
      })
    if (method === 'GET' && path === '/api-keys')
      return send(mode === 'empty' ? [] : keys)
    if (method === 'GET' && path === '/evaluation-options')
      return send({
        strategies: [{ name: 'direct' }, { name: 'reflexion' }],
        sources: [
          { id: 'shared', label: '共享题目', problem_count: 21 },
          { id: 'personal', label: '个人题目', problem_count: 1 },
        ],
      })
    if (method === 'GET' && path === '/evaluation-options/models') {
      const key = url.searchParams.get('api_key_id')
      if (key === 'key-slow') await new Promise((r) => setTimeout(r, 650))
      return send({
        provider: 'openai',
        models: [
          key === 'key-b'
            ? 'model-b'
            : key === 'key-slow'
              ? 'stale-model'
              : 'model-a',
        ],
        complete: key === 'key-b',
      })
    }
    if (method === 'GET' && path === '/evaluation-options/problems') {
      const offset = Number(url.searchParams.get('offset'))
      const source = url.searchParams.get('source')
      const limit = Number(url.searchParams.get('limit'))
      const all = Array.from(
        { length: source === 'personal' ? 1 : 21 },
        (_, index) => ({
          problem_id: source === 'personal' ? 'personal-1' : `p${index + 1}`,
          title: source === 'personal' ? '个人算法题' : `算法题 ${index + 1}`,
          difficulty: 'easy',
          source: source === 'personal' ? 'personal' : 'shared',
        }),
      )
      if (source === 'all')
        all.push({
          problem_id: 'personal-1',
          title: '个人算法题',
          difficulty: 'easy',
          source: 'personal',
        })
      return send({
        items: all.slice(offset, offset + limit),
        total: all.length,
        offset,
        limit,
        has_more: offset + limit < all.length,
      })
    }
    if (
      mode.startsWith('detail-') &&
      path.startsWith('/evaluations/eval-fixture-1')
    ) {
      if (method === 'GET') {
        if (detailGate) await detailGate
        if (detailFailure)
          return route.fulfill({
            status: detailFailure,
            headers,
            json: { message: '详情刷新失败' },
          })
        if (['detail-403', 'detail-404'].includes(mode))
          return route.fulfill({
            status: Number(mode.slice(7)),
            headers,
            json: { message: '任务不可访问' },
          })
        const status = mode.slice(7)
        if (
          !detail.changed &&
          [
            'running',
            'paused',
            'completed',
            'failed',
            'cancelled',
            'future-state',
          ].includes(status)
        )
          detail = {
            ...evaluation,
            status,
            can_start: false,
            can_cancel: ['running', 'paused'].includes(status),
            error_message: ['paused', 'failed'].includes(status)
              ? '预算或供应商失败原因'
              : null,
          }
        if (mode === 'detail-queued')
          detail = { ...evaluation, can_start: false }
        return send(detail)
      }
      if (method === 'POST') {
        await new Promise((r) => setTimeout(r, 150))
        if (path.endsWith('/start')) {
          if (mode === 'detail-start-error' && ++starts === 1)
            return route.fulfill({
              status: 503,
              headers,
              json: { message: '启动失败，请核对' },
            })
          detail = { ...evaluation, can_start: false, changed: true }
        } else if (path.endsWith('/cancel')) {
          if (mode === 'detail-cancel-error')
            return route.fulfill({
              status: 503,
              headers,
              json: { message: '取消失败，请核对' },
            })
          detail = {
            ...evaluation,
            status: mode === 'detail-race' ? 'completed' : 'cancelled',
            can_start: false,
            can_cancel: false,
            changed: true,
          }
          if (mode === 'detail-race')
            return route.fulfill({
              status: 409,
              headers,
              json: { message: '任务已结束' },
            })
        } else throw new Error(`Unexpected detail mutation: ${path}`)
        return send(detail)
      }
    }
    if (method === 'GET' && path === '/evaluations') {
      if (mode === 'list-loading') await listGate
      if (mode === 'list-stale' && url.searchParams.get('status') === 'running')
        await staleGate
      if (failList)
        return route.fulfill({
          status: 503,
          headers,
          json: { message: 'unavailable' },
        })
      const limit = Number(url.searchParams.get('limit'))
      const offset = Number(url.searchParams.get('offset'))
      const status = url.searchParams.get('status')
      let items = Array.from(
        { length: mode === 'list-shrunk' ? 21 : 42 },
        (_, i) => ({
          ...evaluation,
          evaluation_id: `owned-evaluation-${i + 1}`,
          model: 'owned-model',
          strategy_names: ['reflexion'],
          status:
            i === 0
              ? 'future-state'
              : ['pending', 'running', 'completed'][i % 3],
          can_start: false,
          spent_usd: 0.125,
          execution_progress: {
            completed_units: 3,
            total_units: 8,
            percentage: 37.5,
          },
        }),
      )
      if (mode === 'list-empty') items = []
      if (status) items = items.filter((item) => item.status === status)
      return send({
        items: items.slice(offset, offset + limit),
        total: items.length,
        limit,
        offset,
        has_more: offset + limit < items.length,
      })
    }
    if (method === 'POST' && path === '/evaluations') {
      await new Promise((r) => setTimeout(r, 150))
      if (mode === 'unknown')
        return route.fulfill({
          status: 503,
          headers,
          json: { message: '创建响应暂时不可用' },
        })
      return send(evaluation, 201)
    }
    if (method === 'POST' && path === '/evaluations/eval-fixture-1/start') {
      if (mode === 'start-error' && ++starts > 1) {
        detail = { ...evaluation, can_start: false }
        return send(detail)
      }
      return route.fulfill({
        status: 503,
        headers,
        json: { message: '启动服务暂时不可用' },
      })
    }
    if (method === 'GET' && path === '/evaluations/eval-fixture-1') {
      if (mode === 'progress' || mode === 'results-live') {
        const intervalStart = Date.now()
        // 人为拉长请求以暴露并发周期（场景断言请求区间不重叠）
        await new Promise((resolve) => setTimeout(resolve, 120))
        // HTTP 真值递进：progress 帧投递前恒 20%，之后 60%——
        // 锁定「事件触发刷新」而非 start 自身的首次 GET
        const percentage = progressPercentage
        detail = {
          ...evaluation,
          status: 'running',
          can_start: false,
          can_cancel: true,
          execution_progress: {
            completed_units: percentage === 20 ? 0 : 1,
            total_units: 2,
            percentage,
          },
          progress: {
            current: percentage === 20 ? 0 : 1,
            total: 2,
            message: null,
            completed: percentage === 20 ? 0 : 1,
            percentage,
          },
        }
        const response = await send(detail)
        detailIntervals.push([intervalStart, Date.now()])
        detailProgress.push(percentage)
        return response
      }
      return send(detail)
    }
    report.unknown.push(call)
    return route.fulfill({
      status: 599,
      headers,
      json: { message: `Unexpected API: ${method} ${path}` },
    })
  })
  await context.routeWebSocket(/\/api\/v1\/ws\/progress/, (ws) => {
    wsUrls.push(ws.url())
    denyProgress = () => ws.close({ code: 4403 })
    ws.onMessage((message) => {
      const frame = JSON.parse(String(message))
      if (frame.action === 'subscribe') {
        subscriptionAt = Date.now()
        if (mode === 'progress' || mode === 'results-live')
          ws.send(
            JSON.stringify({
              type: 'task.snapshot',
              task_id: frame.task_id,
              data: detail,
            }),
          )
        ws.send(JSON.stringify({ type: 'subscribed', task_id: frame.task_id }))
        advanceProgress = (percentage = 60) => {
          progressPercentage = percentage
          ws.send(
            JSON.stringify({
              type: 'task.progress',
              task_id: frame.task_id,
              data: {
                completed: 1,
                total: 2,
                percentage: 50,
                current_problem: 'p1',
                current_strategy: 'direct',
              },
            }),
          )
        }
      }
    })
  })
  await page.goto(`${base}${entry}`)
  await page.locator('h1').waitFor()
  if (entry === '/evaluations/new') {
    check('创建地址显示真实创建表单', () =>
      assert.equal(new URL(page.url()).pathname, '/evaluations/new'),
    )
    await page.getByRole('heading', { name: '创建评估', exact: true }).waitFor()
  }
  return {
    context,
    page,
    calls,
    errors,
    wsUrls,
    detailIntervals,
    detailProgress,
    resultIntervals,
    holdResult(offset) {
      heldResultOffset = offset
      resultHeld = new Promise((resolve) => {
        markResultHeld = resolve
      })
      resultGate = new Promise((resolve) => {
        releaseResult = resolve
      })
    },
    waitForHeldResult: () => resultHeld,
    releaseResult() {
      heldResultOffset = null
      resultGate = null
      releaseResult()
    },
    failResult: (status) => {
      resultFailure = status
    },
    failResultsList: (failed) => {
      resultsListFailure = failed
    },
    async waitForInitialProgressReconciliation() {
      const deadline = Date.now() + 8000
      while (
        !detailIntervals.some(([started]) => started >= subscriptionAt + 1900)
      ) {
        if (Date.now() > deadline)
          throw new Error('Initial snapshot reconciliation did not complete')
        await new Promise((resolve) => setTimeout(resolve, 10))
      }
    },
    advanceProgress: (percentage) => advanceProgress(percentage),
    denyProgress: () => denyProgress(),
    releaseList,
    releaseStale,
    holdDetail() {
      detailGate = new Promise((resolve) => {
        releaseDetail = resolve
      })
    },
    releaseDetail() {
      releaseDetail()
    },
    failDetail(status) {
      detailFailure = status
    },
    recoverList() {
      failList = false
    },
  }
}
async function choose(page, label, text) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page
    .locator('.ant-select-dropdown:visible .ant-select-item-option')
    .filter({ hasText: new RegExp(`^${text}$`) })
    .click()
  await page.keyboard.press('Escape')
}
async function configure(page) {
  await choose(page, 'API 密钥', '密钥 A · openai')
  await choose(page, '模型', 'model-a')
  await choose(page, '策略', 'direct')
  await page.getByRole('checkbox', { name: '选择题目 p1', exact: true }).check()
}
async function createScenario() {
  report.real.push('creation/detail pages')
  const { page, context, calls, errors } = await fixture()
  await choose(page, 'API 密钥', '密钥 A · openai')
  await page.getByText('模型列表未完整加载', { exact: false }).waitFor()
  await page.getByRole('button', { name: '创建并启动', exact: true }).click()
  for (const message of [
    '请选择已加载的模型',
    '请选择可用策略',
    '请选择当前来源的可用题目',
  ])
    await page.getByText(message, { exact: true }).waitFor()
  check('必填错误阻止请求', () =>
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0),
  )
  await configure(page)
  await choose(page, '题目来源', '个人题目（1）')
  await page.getByText('已选 0 道题目', { exact: true }).waitFor()
  await page
    .getByRole('checkbox', { name: '选择题目 personal-1', exact: true })
    .check()
  await choose(page, '题目来源', '全部来源')
  await page.getByText('已选 0 道题目', { exact: true }).waitFor()
  await page.getByRole('checkbox', { name: '选择题目 p1', exact: true }).check()
  report.assertions.push({
    name: '来源切换清理旧选择，题目来自真实选项响应',
    pass: true,
  })
  await page.getByText('模型列表未完整加载', { exact: false }).waitFor()
  check('模型仅来自接口且不完整状态明确', () =>
    assert.ok(calls.some((c) => c.path === '/evaluation-options/models')),
  )
  await choose(page, 'API 密钥', '密钥 B · openai')
  const clearedModel = await page
    .locator('.ant-form-item')
    .filter({ has: page.getByRole('combobox', { name: '模型', exact: true }) })
    .getByText('model-a', { exact: true })
    .count()
  check('密钥切换立即清除模型', () => assert.equal(clearedModel, 0))
  await choose(page, 'API 密钥', '密钥 SLOW · openai')
  await choose(page, 'API 密钥', '密钥 B · openai')
  await choose(page, '模型', 'model-b')
  await page.waitForTimeout(750)
  await page.getByRole('combobox', { name: '模型', exact: true }).click()
  const staleModels = await page
    .locator('.ant-select-dropdown:visible')
    .getByText('stale-model', { exact: true })
    .count()
  check('迟到的旧密钥模型没有覆盖当前模型', () => assert.equal(staleModels, 0))
  await page.keyboard.press('Escape')
  await choose(page, 'API 密钥', '密钥 A · openai')
  await choose(page, '模型', 'model-a')
  await page.getByRole('button', { name: '下一页题目', exact: true }).click()
  await page
    .getByRole('checkbox', { name: '选择题目 p21', exact: true })
    .check()
  await page.getByRole('button', { name: '上一页题目', exact: true }).click()
  assert.equal(
    await page
      .getByRole('checkbox', { name: '选择题目 p1', exact: true })
      .isChecked(),
    true,
  )
  await page.getByText('已选 2 道题目', { exact: true }).waitFor()
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check()
  await page.getByText('已选 21 道题目', { exact: true }).waitFor()
  await page
    .getByRole('checkbox', { name: '全选当前页', exact: true })
    .uncheck()
  await page.getByText('已选 1 道题目', { exact: true }).waitFor()
  await page.getByRole('checkbox', { name: '选择题目 p1', exact: true }).check()
  await page.getByText('已选 2 道题目', { exact: true }).waitFor()
  report.assertions.push({
    name: '当前页全选与取消不影响其他页选择',
    pass: true,
  })
  await page.getByRole('button', { name: '下一页题目', exact: true }).click()
  await page
    .getByRole('checkbox', { name: '选择题目 p21', exact: true })
    .uncheck()
  await page
    .getByRole('checkbox', { name: '选择题目 p21', exact: true })
    .check()
  await page.getByRole('button', { name: '上一页题目', exact: true }).click()
  check('跨页已核实题目保留选择', () =>
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0),
  )
  await page.getByLabel('预算上限（USD，可选）', { exact: true }).fill('-1')
  await page.getByRole('button', { name: '创建并启动', exact: true }).click()
  await page.getByText('预算必须为有限非负数', { exact: true }).waitFor()
  check('非法预算没有提交', () =>
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0),
  )
  await page.getByLabel('预算上限（USD，可选）', { exact: true }).fill('0')
  await page
    .getByText('预算必须为有限非负数', { exact: true })
    .waitFor({ state: 'hidden', timeout: 2000 })
  report.assertions.push({ name: '修改预算后清理过时字段错误', pass: true })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `no horizontal overflow at ${width}`,
    )
    await page.evaluate(() => {
      document.activeElement?.blur()
      window.scrollTo(0, 0)
    })
    report.assertions.push({ name: `${width}px 无横向溢出`, pass: true })
    if (width === 320) {
      const previous = await page
        .getByRole('button', { name: '上一页题目', exact: true })
        .boundingBox()
      const next = await page
        .getByRole('button', { name: '下一页题目', exact: true })
        .boundingBox()
      check('320px分页按钮同排可比较', () =>
        assert.ok(Math.abs(previous.y - next.y) < 2),
      )
    }
    const file = `create-${width}.png`
    await page.screenshot({ path: resolve(out, file), fullPage: true })
    report.screenshots.push(file)
  }
  for (const variant of ['orbit', 'precision', 'studio']) {
    await page.getByLabel('选择页面风格', { exact: true }).selectOption(variant)
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('主题偏好', { exact: true }).selectOption(theme)
      await page.getByText('已选 2 道题目', { exact: true }).waitFor()
      const budget = await page
        .getByLabel('预算上限（USD，可选）', { exact: true })
        .inputValue()
      check(`${variant}/${theme} 保留创建草稿`, () => assert.equal(budget, '0'))
      await page.evaluate(() => {
        document.activeElement?.blur()
        window.scrollTo(0, 0)
      })
      const contrast = await page
        .locator('.ant-form-item-explain')
        .filter({ hasText: '留空不设置上限' })
        .evaluate((element) => {
          const channels = (value) => value.match(/[0-9.]+/g).map(Number)
          const foreground = channels(getComputedStyle(element).color)
          const background = channels(
            getComputedStyle(element.closest('.panel')).backgroundColor,
          )
          const alpha = foreground[3] ?? 1
          const composite = foreground
            .slice(0, 3)
            .map((v, i) => v * alpha + background[i] * (1 - alpha))
          const lum = (values) =>
            values
              .slice(0, 3)
              .map((v) => v / 255)
              .map((v) =>
                v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
              )
              .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
          return (
            (Math.max(lum(composite), lum(background)) + 0.05) /
            (Math.min(lum(composite), lum(background)) + 0.05)
          )
        })
      check(`${variant}/${theme} 预算帮助文字对比度`, () =>
        assert.ok(contrast >= 4.5, `contrast ${contrast}`),
      )
      const file = `create-${variant}-${theme}.png`
      await page.screenshot({ path: resolve(out, file), fullPage: true })
      report.screenshots.push(file)
    }
  }
  // Native submit plus two click events in one turn exercise the synchronous mutex.
  await page
    .getByRole('button', { name: '创建并启动', exact: true })
    .evaluate((button) => {
      button.click()
      button.click()
      button.form.requestSubmit()
    })
  await page.keyboard.press('Enter')
  await page.waitForURL('**/evaluations/eval-fixture-1')
  await page.getByText('任务已创建，启动尚未确认', { exact: true }).waitFor()
  await page.getByText('eval-fixture-1', { exact: true }).waitFor()
  const creates = calls.filter(
    (c) => c.method === 'POST' && c.path === '/evaluations',
  )
  check('重复点击与回车只创建一次', () => assert.equal(creates.length, 1))
  check('payload包含跨页选题且只含有效字段', () =>
    assert.deepEqual(creates[0].payload, {
      api_key_id: 'key-a',
      model: 'model-a',
      problem_ids: ['p1', 'p21'],
      strategy_names: ['direct'],
      budget_cap_usd: 0,
    }),
  )
  check('201后只启动确认的evaluation ID一次', () =>
    assert.deepEqual(
      calls
        .filter((c) => c.method === 'POST' && c.path.endsWith('/start'))
        .map((c) => c.path),
      ['/evaluations/eval-fixture-1/start'],
    ),
  )
  await page.screenshot({
    path: resolve(out, 'create-start-error.png'),
    fullPage: true,
  })
  report.screenshots.push('create-start-error.png')
  await page.getByRole('button', { name: '启动任务', exact: true }).click()
  await page
    .getByRole('region', { name: '评估详情', exact: true })
    .getByText('已入队，等待执行', { exact: true })
    .waitFor()
  check('创建后启动失败在详情重试只start、不再次create', () => {
    assert.equal(
      calls.filter((c) => c.method === 'POST' && c.path === '/evaluations')
        .length,
      1,
    )
    assert.equal(
      calls.filter((c) => c.method === 'POST' && c.path.endsWith('/start'))
        .length,
      2,
    )
  })
  check('浏览器无运行异常', () => assert.deepEqual(errors, []))
  await context.close()
  const unknown = await fixture('unknown')
  await configure(unknown.page)
  await unknown.page
    .getByRole('button', { name: '创建并启动', exact: true })
    .click()
  await unknown.page.getByText('创建结果尚未确认', { exact: true }).waitFor()
  assert.equal(
    await unknown.page
      .getByRole('link', { name: '查看任务列表', exact: true })
      .count(),
    1,
  )
  await unknown.page
    .getByRole('button', { name: '确认核对后开始新评估', exact: true })
    .click()
  assert.equal(
    await unknown.page
      .getByRole('heading', { name: '创建评估', exact: true })
      .count(),
    1,
  )
  check('未知创建仅显式核对后开始新操作且不自动重发', () =>
    assert.equal(unknown.calls.filter((c) => c.method === 'POST').length, 1),
  )
  await unknown.context.close()
  const empty = await fixture('empty')
  await empty.page.getByText('还没有可用密钥', { exact: false }).waitFor()
  assert.equal(
    await empty.page
      .getByRole('button', { name: '创建并启动', exact: true })
      .isDisabled(),
    true,
  )
  check('缺少选项禁提交并显示密钥管理入口', () =>
    assert.equal(empty.calls.filter((c) => c.method === 'POST').length, 0),
  )
  await empty.context.close()
}

async function securityScenario() {
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route(`${base}/`, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;window.ready=true;</script>`,
    }),
  )
  await page.goto(`${base}/`)
  await page.waitForFunction(() => window.ready)
  const result = await page.evaluate(async () => {
    const mainText = await (await fetch('/src/main.tsx')).text()
    const sessionText = await (
      await fetch('/src/evaluations/session.tsx')
    ).text()
    const dependency = (source, name) =>
      source.match(
        new RegExp('"(/node_modules/[^"]*/' + name + '\\.js[^"]*)"'),
      )[1]
    const { default: React } = await import(dependency(sessionText, 'react'))
    const {
      default: { createRoot },
    } = await import(dependency(mainText, 'react-dom_client'))
    const { MemoryRouter } = await import(
      dependency(sessionText, 'react-router-dom')
    )
    const { EvaluationSessionProvider, useEvaluationSession } =
      await import('/src/evaluations/session.tsx')
    const { useAuthStore } = await import('/src/store/auth.ts')
    const draft = {
      api_key_id: 'key-1',
      model: 'initialized-model',
      problem_ids: ['p-1'],
      strategy_names: ['direct'],
      budget_cap_usd: '',
    }
    const evaluation = {
      evaluation_id: 'eval-old',
      created_at: '2026-10-21',
      updated_at: '2026-10-21',
      status: 'pending',
      can_start: true,
      can_cancel: true,
      execution_progress: { completed_units: 0, total_units: 1, percentage: 0 },
      strategy_names: ['direct'],
      model: 'initialized-model',
      problem_count: 1,
      spent_usd: 0,
      budget_cap_usd: null,
      error_message: null,
      progress: null,
    }
    const waitFor = async (condition) => {
      const deadline = Date.now() + 3000
      while (!condition()) {
        if (Date.now() > deadline)
          throw new Error('React fixture did not settle')
        await new Promise((resolve) => setTimeout(resolve, 10))
      }
    }
    async function mount(marker) {
      const calls = []
      let resolveCreate
      const http = {
        post: (url, payload) => {
          calls.push({ method: 'POST', url, payload })
          if (url === '/evaluations')
            return new Promise((resolve) => {
              resolveCreate = resolve
            })
          return Promise.resolve(evaluation)
        },
        get: async (url) => {
          calls.push({ method: 'GET', url })
          return evaluation
        },
      }
      useAuthStore.setState({ session: { marker }, httpClient: () => http })
      const events = []
      const stores = []
      let setups = 0
      function Consumer() {
        const session = useEvaluationSession()
        if (!stores.includes(session.creationStore))
          stores.push(session.creationStore)
        React.useEffect(() => {
          const store = session.creationStore
          events.push({
            event: 'child-setup-before',
            owner: store.getState().owner,
          })
          const unsubscribe = store.subscribe((state) =>
            events.push({
              event: 'state',
              owner: state.owner,
              model: state.draft.model,
            }),
          )
          store.getState().setDraft(draft)
          events.push({
            event: 'child-setup-after',
            model: store.getState().draft.model,
          })
          setups++
          return unsubscribe
        }, [session])
        return null
      }
      const host = document.createElement('div')
      document.body.appendChild(host)
      const root = createRoot(host)
      root.render(
        React.createElement(
          React.StrictMode,
          null,
          React.createElement(
            MemoryRouter,
            null,
            React.createElement(
              EvaluationSessionProvider,
              null,
              React.createElement(Consumer),
            ),
          ),
        ),
      )
      await waitFor(() => setups === 2)
      await Promise.resolve()
      return {
        root,
        stores,
        calls,
        events,
        resolve: () => resolveCreate(evaluation),
        waitFor,
        setups: () => setups,
        host,
      }
    }
    const replay = await mount('replay-session')
    const replayState = replay.stores[0].getState()
    const strictReplay = {
      owner: replayState.owner,
      model: replayState.draft.model,
      events: [...replay.events],
      stores: replay.stores.length,
    }
    const oldEditing = replay.stores[0]
    replay.root.unmount()
    oldEditing.getState().setDraft({ model: 'stale-model' })
    const immediatelyAfterUnmount = oldEditing.getState().draft.model
    const staleSubmit = oldEditing.getState().submit()
    const immediatelyAfterSubmit = oldEditing.getState().phase
    const staleRetry = oldEditing.getState().retryStart('existing')
    const immediatelyAfterRetry = {
      phase: oldEditing.getState().phase,
      evaluationId: oldEditing.getState().evaluationId,
    }
    await Promise.all([staleSubmit, staleRetry])
    await Promise.resolve()
    const unmountEditing = {
      immediatelyAfterUnmount,
      immediatelyAfterSubmit,
      immediatelyAfterRetry,
      owner: oldEditing.getState().owner,
      model: oldEditing.getState().draft.model,
      calls: replay.calls,
    }

    const pending = await mount('pending-session')
    const pendingStore = pending.stores[0]
    pendingStore.getState().setDraft(draft)
    const pendingTask = pendingStore.getState().submit()
    await pending.waitFor(() => pending.calls.length === 1)
    pending.resolve()
    pending.root.unmount()
    await pendingTask
    const unmountPending = {
      calls: pending.calls,
      owner: pendingStore.getState().owner,
      model: pendingStore.getState().draft.model,
      evaluationId: pendingStore.getState().evaluationId,
    }

    const marker = await mount('marker-old')
    const oldStore = marker.stores[0]
    oldStore.getState().setDraft(draft)
    const markerTask = oldStore.getState().submit()
    await marker.waitFor(() => marker.calls.length === 1)
    useAuthStore.setState({ session: { marker: 'marker-new' } })
    // Auth marker invalidates old actions even before React commits the new scope.
    oldStore.getState().setDraft({ model: 'stale-marker-model' })
    await oldStore.getState().retryStart('existing')
    marker.resolve()
    await markerTask
    await marker.waitFor(
      () => marker.stores.length === 2 && marker.setups() === 4,
    )
    await Promise.resolve()
    const newStore = marker.stores[1]
    const markerChange = {
      calls: marker.calls,
      distinct: oldStore !== newStore,
      oldOwner: oldStore.getState().owner,
      oldModel: oldStore.getState().draft.model,
      oldId: oldStore.getState().evaluationId,
      newOwner: newStore.getState().owner,
      newModel: newStore.getState().draft.model,
    }
    marker.root.unmount()
    await Promise.resolve()
    return { strictReplay, unmountEditing, unmountPending, markerChange }
  })
  assert.deepEqual(errors, [])
  assert.equal(result.strictReplay.owner, 'replay-session')
  assert.equal(
    result.strictReplay.model,
    'initialized-model',
    'StrictMode replay preserves child-initialized draft',
  )
  assert.equal(result.strictReplay.stores, 1)
  assert.ok(
    result.strictReplay.events.every((event) => event.owner !== null),
    'Replay never publishes a null owner',
  )
  assert.equal(
    result.unmountEditing.immediatelyAfterUnmount,
    'initialized-model',
    'Unmount immediately rejects stale draft writes',
  )
  assert.equal(
    result.unmountEditing.immediatelyAfterSubmit,
    'editing',
    'Unmount rejects submit before it publishes creating',
  )
  assert.deepEqual(
    result.unmountEditing.immediatelyAfterRetry,
    { phase: 'editing', evaluationId: null },
    'Unmount rejects retry before it publishes created',
  )
  assert.deepEqual(
    result.unmountEditing.calls,
    [],
    'Unmount immediately rejects submit/retry',
  )
  assert.equal(result.unmountEditing.owner, null)
  assert.equal(
    result.unmountEditing.model,
    '',
    'Real unmount clears draft after its cleanup microtask',
  )
  for (const scenario of [result.unmountPending, result.markerChange]) {
    assert.deepEqual(
      scenario.calls.map((call) => call.url),
      ['/evaluations'],
      'Late 201 cannot start after unmount/marker change',
    )
  }
  assert.equal(result.unmountPending.owner, null)
  assert.equal(result.unmountPending.model, '')
  assert.equal(result.unmountPending.evaluationId, null)
  assert.equal(result.markerChange.distinct, true)
  assert.equal(result.markerChange.oldOwner, null)
  assert.equal(result.markerChange.oldModel, '')
  assert.equal(result.markerChange.oldId, null)
  assert.equal(result.markerChange.newOwner, 'marker-new')
  assert.equal(result.markerChange.newModel, 'initialized-model')

  report.assertions.push({
    name: '真实 React StrictMode 重放、卸载和换 marker 拒绝旧 actions 与迟到201',
    pass: true,
    result,
  })
  await page.close()
}

async function listLifecycleScenario() {
  report.replaced.push(
    'list lifecycle only: isolated HTML and in-memory list loader (ignores AbortSignal)',
  )
  const page = await browser.newPage()
  await page.route(`${base}/`, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;window.ready=true;</script>`,
    }),
  )
  await page.goto(`${base}/`)
  await page.waitForFunction(() => window.ready)
  const result = await page.evaluate(async () => {
    const mainText = await (await fetch('/src/main.tsx')).text()
    const sessionText = await (
      await fetch('/src/evaluations/session.tsx')
    ).text()
    const dependency = (source, name) =>
      source.match(
        new RegExp('"(/node_modules/[^"]*/' + name + '\\.js[^"]*)"'),
      )[1]
    const { default: React } = await import(dependency(sessionText, 'react'))
    const {
      default: { createRoot },
    } = await import(dependency(mainText, 'react-dom_client'))
    const { useList } = await import('/src/evaluations/useList.ts')
    const { ApiClientError } = await import('/src/auth/http.ts')
    const requests = []
    const snapshots = []
    let reload
    // Deliberately ignore cancellation: isolation must hold independently.
    const load = (query, signal) =>
      new Promise((resolve, reject) =>
        requests.push({ query, signal, resolve, reject }),
      )
    function Harness({ owner, status }) {
      const state = useList(load, { status, limit: 20, offset: 0 }, owner)
      React.useLayoutEffect(() => {
        reload = state.reload
        snapshots.push({
          owner,
          query: status,
          status: state.status,
          rows: state.data?.items ?? null,
          error: state.error,
        })
      })
      return null
    }
    const root = createRoot(document.getElementById('root'))
    const render = (owner, status) =>
      root.render(
        React.createElement(
          React.StrictMode,
          null,
          React.createElement(Harness, { owner, status }),
        ),
      )
    const waitFor = async (condition) => {
      const deadline = Date.now() + 3000
      while (!condition()) {
        if (Date.now() > deadline)
          throw new Error('List lifecycle did not settle')
        await new Promise((resolve) => setTimeout(resolve, 10))
      }
    }
    const tick = () => new Promise((resolve) => setTimeout(resolve, 40))
    const response = (items) => ({
      items,
      total: items.length,
      limit: 20,
      offset: 0,
      has_more: false,
    })
    const last = () => snapshots.at(-1)
    render('owner-A', 'running')
    await waitFor(() => requests.length >= 2)
    const staleQueries = requests.slice()
    render('owner-A', 'completed')
    await waitFor(() =>
      requests.some((request) => request.query.status === 'completed'),
    )
    requests.at(-1).resolve(response(['A-completed']))
    await waitFor(() => last().rows?.[0] === 'A-completed')
    for (const request of staleQueries) request.resolve(response(['A-running']))
    await tick()
    const afterStaleQuery = last()
    let count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    const staleOwner = requests.at(-1)
    render('owner-B', 'completed')
    await waitFor(
      () => last().owner === 'owner-B' && requests.at(-1) !== staleOwner,
    )
    const initialOwnerB = snapshots.find(
      (snapshot) => snapshot.owner === 'owner-B',
    )
    requests.at(-1).resolve(response(['B-completed']))
    await waitFor(() => last().rows?.[0] === 'B-completed')
    staleOwner.resolve(response(['A-late']))
    await tick()
    const afterStaleOwner = last()
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    requests.at(-1).reject(new ApiClientError(''))
    await waitFor(() => last().status === 'error')
    const error = last()
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    requests.at(-1).resolve(response([]))
    await waitFor(() => last().status === 'ready')
    const empty = last()
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    const unmounted = requests.at(-1)
    root.unmount()
    const commitsAtUnmount = snapshots.length
    unmounted.resolve(response(['after-unmount']))
    await tick()
    return {
      afterStaleQuery,
      initialOwnerB,
      afterStaleOwner,
      error,
      empty,
      unmountAborted: unmounted.signal.aborted,
      commitsAtUnmount,
      commitsAfterUnmount: snapshots.length,
      leaked: snapshots.some(
        (snapshot) =>
          (snapshot.owner === 'owner-B' &&
            snapshot.rows?.some((row) => row.startsWith('A-'))) ||
          (snapshot.query === 'completed' &&
            snapshot.rows?.includes('A-running')),
      ),
    }
  })
  check('忽略AbortSignal的旧查询不能覆盖新查询', () =>
    assert.deepEqual(result.afterStaleQuery.rows, ['A-completed']),
  )
  check('换owner首个提交立即隐藏旧数据', () =>
    assert.deepEqual(
      { status: result.initialOwnerB.status, rows: result.initialOwnerB.rows },
      { status: 'loading', rows: null },
    ),
  )
  check('旧owner迟到不写入新会话或短暂闪现', () => {
    assert.deepEqual(result.afterStaleOwner.rows, ['B-completed'])
    assert.equal(result.leaked, false)
  })
  check('失败不变空集，重试后可呈现合法空页', () => {
    assert.equal(result.error.status, 'error')
    assert.equal(result.error.rows, null)
    assert.ok(result.error.error)
    assert.equal(result.empty.status, 'ready')
    assert.deepEqual(result.empty.rows, [])
  })
  check('卸载取消请求且迟到完成不再提交', () => {
    assert.equal(result.unmountAborted, true)
    assert.equal(result.commitsAfterUnmount, result.commitsAtUnmount)
  })
  await page.close()
}

async function listScenario() {
  report.replaced.push('HTTP GET /api/v1/evaluations list/filter/page')
  report.real.push('owned evaluation list page', 'useList lifecycle')
  const loading = await fixture('list-loading', '/evaluations')
  await loading.page
    .getByText('正在加载评估任务…', { exact: true })
    .waitFor({ timeout: 5000 })
  check('加载不是空集或旧Mock行', () =>
    assert.equal(
      loading.calls.filter((c) => c.path === '/evaluations').length > 0,
      true,
    ),
  )
  assert.equal(
    await loading.page.getByText('还没有评估任务', { exact: true }).count(),
    0,
  )
  loading.releaseList()
  const table = loading.page.getByRole('table', {
    name: '评估任务列表',
    exact: true,
  })
  await table
    .getByRole('link', { name: 'owned-evaluation-1', exact: true })
    .waitFor()
  assert.equal(await table.getByRole('row').count(), 21)
  assert.equal(
    await table.getByText('owned-model', { exact: true }).count(),
    20,
  )
  await table.getByText('未知状态（future-state）', { exact: true }).waitFor()
  await table.getByText('已入队，等待执行', { exact: true }).first().waitFor()
  assert.equal(await table.getByText('37.5%', { exact: false }).count(), 20)
  check('20条真实任务和开放状态/服务端进度', () =>
    assert.equal(
      loading.calls.some(
        (c) =>
          c.path === '/evaluations' &&
          c.query.includes('limit=20') &&
          c.query.includes('offset=0'),
      ),
      true,
    ),
  )
  assert.equal(
    await table
      .getByRole('link', { name: 'owned-evaluation-1', exact: true })
      .getAttribute('href'),
    '/evaluations/owned-evaluation-1',
  )
  await loading.page
    .getByRole('button', { name: '下一页任务', exact: true })
    .click()
  await table
    .getByRole('link', { name: 'owned-evaluation-21', exact: true })
    .waitFor()
  check('第二页URL和请求均为limit20/offset20', () => {
    assert.equal(new URL(loading.page.url()).searchParams.get('offset'), '20')
    assert.ok(
      loading.calls.some(
        (c) => c.path === '/evaluations' && c.query === '?limit=20&offset=20',
      ),
    )
  })
  await loading.page.reload()
  await table
    .getByRole('link', { name: 'owned-evaluation-21', exact: true })
    .waitFor()
  report.assertions.push({ name: '刷新保留分页', pass: true })
  await choose(loading.page, '任务状态', '已完成')
  await table
    .getByRole('link', { name: 'owned-evaluation-3', exact: true })
    .waitFor()
  check('筛选写入URL并清零offset', () => {
    const params = new URL(loading.page.url()).searchParams
    assert.equal(params.get('status'), 'completed')
    assert.equal(params.get('offset'), '0')
    assert.ok(
      loading.calls.some(
        (c) => c.query === '?status=completed&limit=20&offset=0',
      ),
    )
  })
  await loading.page.goBack()
  await table
    .getByRole('link', { name: 'owned-evaluation-40', exact: true })
    .waitFor()
  report.assertions.push({ name: '浏览器后退恢复旧分页', pass: true })
  const beforeStyles = loading.calls.filter(
    (call) => call.path === '/evaluations',
  ).length
  for (const variant of ['orbit', 'precision', 'studio']) {
    await loading.page
      .getByLabel('选择页面风格', { exact: true })
      .selectOption(variant)
    await table
      .getByRole('link', { name: 'owned-evaluation-40', exact: true })
      .waitFor()
    check(`${variant}保留URL分页与已加载任务`, () => {
      assert.equal(new URL(loading.page.url()).searchParams.get('offset'), '20')
      assert.equal(
        loading.calls.filter((call) => call.path === '/evaluations').length,
        beforeStyles,
      )
    })
  }
  await loading.page
    .getByRole('button', { name: '下一页任务', exact: true })
    .click()
  await table
    .getByRole('link', { name: 'owned-evaluation-41', exact: true })
    .waitFor()
  assert.equal(await table.getByRole('row').count(), 3)
  assert.equal(
    await loading.page
      .getByRole('button', { name: '下一页任务', exact: true })
      .isDisabled(),
    true,
  )
  await loading.page
    .getByRole('button', { name: '上一页任务', exact: true })
    .click()
  await table
    .getByRole('link', { name: 'owned-evaluation-40', exact: true })
    .waitFor()
  report.assertions.push({
    name: '最后一页只显示剩余记录并禁用下一页，可返回上一页',
    pass: true,
  })
  for (const width of [390, 1440]) {
    await loading.page.setViewportSize({ width, height: 1000 })
    assert.ok(
      await loading.page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `${width}px page overflow`,
    )
    const file = `list-${width}.png`
    await loading.page.screenshot({ path: resolve(out, file), fullPage: true })
    report.screenshots.push(file)
  }
  check('列表浏览器无异常', () => assert.deepEqual(loading.errors, []))
  await loading.context.close()

  const error = await fixture(
    'list-error',
    '/evaluations?status=completed&limit=20&offset=0',
  )
  await error.page.getByRole('alert').waitFor()
  assert.equal(
    await error.page.getByText('还没有评估任务', { exact: true }).count(),
    0,
  )
  error.recoverList()
  await error.page.getByRole('button', { name: /^重\s*试$/ }).click()
  await error.page
    .getByRole('table', { name: '评估任务列表' })
    .getByRole('link', { name: 'owned-evaluation-3', exact: true })
    .waitFor()
  check('503错误不伪装空集，重试保留筛选', () =>
    assert.ok(
      error.calls
        .filter((c) => c.path === '/evaluations')
        .every((c) => c.query === '?status=completed&limit=20&offset=0'),
    ),
  )
  await error.context.close()

  for (const mode of ['list-empty', 'list-shrunk']) {
    const item = await fixture(mode, '/evaluations?limit=20&offset=80')
    if (mode === 'list-empty') {
      await item.page.getByText('还没有评估任务', { exact: true }).waitFor()
      assert.equal(
        await item.page
          .getByRole('link', { name: '创建首个评估', exact: true })
          .getAttribute('href'),
        '/evaluations/new',
      )
    } else {
      await item.page
        .getByRole('table', { name: '评估任务列表' })
        .getByRole('link', { name: 'owned-evaluation-21', exact: true })
        .waitFor()
    }
    check(`${mode}超页回到有效offset`, () => {
      const expectedOffset = mode === 'list-empty' ? '0' : '20'
      assert.equal(
        new URL(item.page.url()).searchParams.get('offset'),
        expectedOffset,
      )
      assert.ok(
        item.calls.some(
          (c) =>
            c.path === '/evaluations' &&
            c.query === `?limit=20&offset=${expectedOffset}`,
        ),
      )
    })
    await item.context.close()
  }
  const filtered = await fixture(
    'list',
    '/evaluations?status=paused&limit=20&offset=0',
  )
  await filtered.page
    .getByText('没有符合筛选的评估任务', { exact: true })
    .waitFor()
  await filtered.page
    .getByRole('button', { name: '清除筛选', exact: true })
    .click()
  await filtered.page
    .getByRole('table', { name: '评估任务列表' })
    .getByRole('link', { name: 'owned-evaluation-1', exact: true })
    .waitFor()
  check('筛选空集可清除筛选，和账号空集区别显示', () =>
    assert.equal(
      new URL(filtered.page.url()).searchParams.has('status'),
      false,
    ),
  )
  await filtered.context.close()
  const stale = await fixture(
    'list-stale',
    '/evaluations?status=running&limit=20&offset=0',
  )
  await stale.page.getByText('正在加载评估任务…', { exact: true }).waitFor()
  await choose(stale.page, '任务状态', '已完成')
  const currentTable = stale.page.getByRole('table', { name: '评估任务列表' })
  await currentTable
    .getByRole('link', { name: 'owned-evaluation-3', exact: true })
    .waitFor()
  stale.releaseStale()
  await stale.page.waitForTimeout(100)
  assert.equal(
    await currentTable.getByText('运行中', { exact: true }).count(),
    0,
  )
  check('旧筛选迟到不覆盖新筛选', () =>
    assert.equal(
      new URL(stale.page.url()).searchParams.get('status'),
      'completed',
    ),
  )
  await stale.context.close()
  await listLifecycleScenario()
}

async function detailLifecycleScenario() {
  const page = await browser.newPage()
  await page.route(`${base}/`, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;window.ready=true;</script>`,
    }),
  )
  await page.goto(`${base}/`)
  await page.waitForFunction(() => window.ready)
  const result = await page.evaluate(async () => {
    const main = await (await fetch('/src/main.tsx')).text()
    const session = await (await fetch('/src/evaluations/session.tsx')).text()
    const dependency = (source, name) =>
      source.match(
        new RegExp('"(/node_modules/[^"]*/' + name + '\\.js[^"]*)"'),
      )[1]
    const { default: React } = await import(dependency(session, 'react'))
    const {
      default: { createRoot },
    } = await import(dependency(main, 'react-dom_client'))
    const { useEvaluation } = await import('/src/evaluations/useEvaluation.ts')
    const requests = [],
      snapshots = []
    let reload
    const client = {
      get: (id, signal) =>
        new Promise((resolve, reject) =>
          requests.push({ id, signal, resolve, reject }),
        ),
    }
    function Harness({ id, owner }) {
      const state = useEvaluation(client, id, owner)
      React.useLayoutEffect(() => {
        reload = state.reload
        snapshots.push({
          id,
          owner,
          data: state.data?.model,
          loading: state.loading,
          error: state.error,
        })
      })
      return null
    }
    const root = createRoot(document.getElementById('root'))
    const render = (id, owner) =>
      root.render(
        React.createElement(
          React.StrictMode,
          null,
          React.createElement(Harness, { id, owner }),
        ),
      )
    const waitFor = async (condition) => {
      const deadline = Date.now() + 3000
      while (!condition()) {
        if (Date.now() > deadline)
          throw new Error('Detail lifecycle did not settle')
        await new Promise((r) => setTimeout(r, 10))
      }
    }
    const tick = () => new Promise((r) => setTimeout(r, 40))
    const last = () => snapshots.at(-1)
    render('task-A', 'owner-A')
    await waitFor(() => requests.length >= 2)
    const staleRoute = [...requests]
    render('task-B', 'owner-A')
    await waitFor(() => requests.at(-1).id === 'task-B')
    requests.at(-1).resolve({ model: 'B-current' })
    await waitFor(() => last().data === 'B-current')
    staleRoute.forEach((r) => r.resolve({ model: 'A-late' }))
    await tick()
    const route = last()
    let count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    const staleRefresh = requests.at(-1)
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    requests.at(-1).resolve({ model: 'B-newer' })
    await waitFor(() => last().data === 'B-newer')
    staleRefresh.resolve({ model: 'B-older' })
    await tick()
    const refresh = last()
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    const staleOwner = requests.at(-1)
    render('task-B', 'owner-B')
    await waitFor(
      () => requests.at(-1) !== staleOwner && last().owner === 'owner-B',
    )
    const firstOwner = snapshots.find((s) => s.owner === 'owner-B')
    requests.at(-1).resolve({ model: 'owner-B-current' })
    await waitFor(() => last().data === 'owner-B-current')
    staleOwner.reject(new Error('owner-A-late-error'))
    await tick()
    const owner = last()
    count = requests.length
    reload()
    await waitFor(() => requests.length > count)
    const unmounted = requests.at(-1)
    root.unmount()
    const commits = snapshots.length
    unmounted.resolve({ model: 'unmounted' })
    await tick()
    return {
      route,
      refresh,
      firstOwner,
      owner,
      aborted: unmounted.signal.aborted,
      commits,
      finalCommits: snapshots.length,
      leaked: snapshots.some(
        (s) =>
          s.data === 'A-late' ||
          s.data === 'B-older' ||
          s.error === 'owner-A-late-error',
      ),
    }
  })
  check('详情忽略旧路由与旧刷新响应，即使transport忽略AbortSignal', () => {
    assert.equal(result.route.data, 'B-current')
    assert.equal(result.refresh.data, 'B-newer')
    assert.equal(result.leaked, false)
  })
  check('详情换owner立即隐藏旧快照，旧错误不污染新会话', () => {
    assert.equal(result.firstOwner.data, undefined)
    assert.equal(result.firstOwner.loading, true)
    assert.equal(result.owner.data, 'owner-B-current')
    assert.equal(result.owner.error, undefined)
  })
  check('详情卸载中止GET且迟到响应不再提交', () => {
    assert.equal(result.aborted, true)
    assert.equal(result.commits, result.finalCommits)
  })
  await page.close()
}

async function detailScenario() {
  await detailLifecycleScenario()
  report.real.push(
    'evaluation detail page',
    'useEvaluation',
    'shared action coordinator',
  )
  report.replaced.push('HTTP evaluation detail/start/cancel responses')
  for (const [mode, label] of [
    ['pending', '待启动'],
    ['queued', '已入队，等待执行'],
    ['running', '运行中'],
    ['paused', '已暂停'],
    ['completed', '已完成'],
    ['failed', '失败'],
    ['cancelled', '已取消'],
    ['future-state', '未知状态（future-state）'],
  ]) {
    const h = await fixture(`detail-${mode}`, '/evaluations/eval-fixture-1')
    const region = h.page.getByRole('region', { name: '评估详情', exact: true })
    await region.getByText(label, { exact: true }).waitFor({ timeout: 5000 })
    for (const value of ['model-a', 'direct', '未设置上限'])
      await region.getByText(value, { exact: true }).waitFor()
    if (['paused', 'failed'].includes(mode))
      await region.getByText('预算或供应商失败原因', { exact: true }).waitFor()
    assert.equal(
      await h.page
        .getByRole('button', { name: '启动任务', exact: true })
        .count(),
      mode === 'pending' ? 1 : 0,
    )
    assert.equal(
      await h.page
        .getByRole('button', { name: '取消任务', exact: true })
        .count(),
      ['pending', 'queued', 'running', 'paused'].includes(mode) ? 1 : 0,
    )
    await h.page.reload()
    await region.getByText(label, { exact: true }).waitFor()
    await h.page.getByRole('button', { name: '刷新任务', exact: true }).click()
    await region.getByText(label, { exact: true }).waitFor()
    check(`${mode}直接访问、刷新与能力来自GET`, () => {
      assert.equal(h.calls.filter((c) => c.method === 'POST').length, 0)
      assert.ok(h.calls.some((c) => c.path === '/evaluations/eval-fixture-1'))
    })
    if (mode === 'running') {
      for (const variant of ['orbit', 'precision', 'studio']) {
        await h.page
          .getByLabel('选择页面风格', { exact: true })
          .selectOption(variant)
        for (const theme of ['light', 'dark']) {
          await h.page
            .getByLabel('主题偏好', { exact: true })
            .selectOption(theme)
          for (const width of [320, 1440]) {
            await h.page.setViewportSize({ width, height: 1000 })
            assert.ok(
              await h.page.evaluate(
                () => document.documentElement.scrollWidth <= window.innerWidth,
              ),
            )
            const file = `detail-${variant}-${theme}-${width}.png`
            await h.page.screenshot({
              path: resolve(out, file),
              fullPage: true,
            })
            report.screenshots.push(file)
          }
        }
      }
      report.assertions.push({
        name: '三风格浅深主题320/1440px无溢出',
        pass: true,
      })
    }
    assert.deepEqual(h.errors, [])
    await h.context.close()
  }
  for (const action of ['启动任务', '取消任务']) {
    const h = await fixture('detail-pending', '/evaluations/eval-fixture-1')
    await h.page
      .getByRole('region', { name: '评估详情' })
      .getByText('待启动', { exact: true })
      .waitFor()
    h.holdDetail()
    const count = h.calls.length
    await h.page.getByRole('button', { name: action, exact: true }).click()
    await h.page.waitForFunction(
      () =>
        document
          .querySelector('[aria-label="评估详情"]')
          .getAttribute('aria-busy') === 'true',
    )
    assert.ok(h.calls.length > count)
    await h.page
      .getByRole('link', { name: '返回任务列表', exact: true })
      .click()
    await h.page.getByRole('link', { name: '创建评估', exact: true }).waitFor()
    h.releaseDetail()
    await h.page.waitForTimeout(100)
    check(`${action}预检时离页不继续POST`, () =>
      assert.equal(h.calls.filter((c) => c.method === 'POST').length, 0),
    )
    await h.page.getByRole('link', { name: '创建评估', exact: true }).click()
    await h.page
      .getByRole('combobox', { name: 'API 密钥', exact: true })
      .waitFor()
    check(`${action}离页保留新建表单可用`, () => assert.deepEqual(h.errors, []))
    await h.context.close()
  }
  const refresh = await fixture('detail-pending', '/evaluations/eval-fixture-1')
  const region = refresh.page.getByRole('region', {
    name: '评估详情',
    exact: true,
  })
  await region.getByText('model-a', { exact: true }).waitFor()
  refresh.failDetail(503)
  await refresh.page
    .getByRole('button', { name: '刷新任务', exact: true })
    .click()
  await refresh.page.getByRole('alert').waitFor()
  await region.getByText('model-a', { exact: true }).waitFor()
  assert.equal(
    await refresh.page
      .getByRole('button', { name: '启动任务', exact: true })
      .isDisabled(),
    true,
  )
  refresh.failDetail(403)
  await refresh.page
    .getByRole('button', { name: '刷新任务', exact: true })
    .click()
  await region
    .getByText('model-a', { exact: true })
    .waitFor({ state: 'hidden' })
  refresh.failDetail(0)
  await refresh.page
    .getByRole('button', { name: '刷新任务', exact: true })
    .click()
  await region.getByText('model-a', { exact: true }).waitFor()
  await refresh.page
    .getByText('实时进度已连接', { exact: true })
    .waitFor({ timeout: 5000 })
  check('HTTP403显式重试后恢复实时订阅', () =>
    assert.ok(refresh.wsUrls.length >= 2),
  )
  check('刷新503保留数据并禁操作，403清除数据，重试恢复', () =>
    assert.equal(refresh.calls.filter((c) => c.method === 'POST').length, 0),
  )
  await refresh.context.close()
  for (const status of [403, 404]) {
    const h = await fixture(`detail-${status}`, '/evaluations/eval-fixture-1')
    await h.page.getByRole('alert').waitFor()
    assert.equal(
      await h.page
        .getByRole('button', { name: '启动任务', exact: true })
        .count(),
      0,
    )
    assert.equal(
      await h.page
        .getByRole('button', { name: '取消任务', exact: true })
        .count(),
      0,
    )
    check(`${status}显示错误且无动作`, () =>
      assert.equal(h.calls.filter((c) => c.method === 'POST').length, 0),
    )
    await h.context.close()
  }
  for (const mode of ['pending', 'cancel-error', 'race', 'start-error']) {
    const h = await fixture(`detail-${mode}`, '/evaluations/eval-fixture-1')
    const region = h.page.getByRole('region', { name: '评估详情', exact: true })
    await region.getByText('待启动', { exact: true }).waitFor()
    const start = mode === 'start-error'
    const button = h.page.getByRole('button', {
      name: start ? '启动任务' : '取消任务',
      exact: true,
    })
    await button.evaluate((element) => {
      element.click()
      element.click()
    })
    if (start || mode === 'cancel-error') {
      await h.page.getByRole('alert').waitFor()
      await region.getByText('待启动', { exact: true }).waitFor()
      if (start) {
        await button.click()
        await region.getByText('已入队，等待执行', { exact: true }).waitFor()
      }
    } else
      await region
        .getByText(mode === 'race' ? '已完成' : '已取消', { exact: true })
        .waitFor()
    const mutations = h.calls.filter((c) => c.method === 'POST')
    assert.equal(mutations.length, start ? 2 : 1)
    assert.ok(
      mutations.every(
        (c) =>
          c.path ===
          `/evaluations/eval-fixture-1/${start ? 'start' : 'cancel'}`,
      ),
    )
    check(`${mode}真实动作、失败、终态竞争及互斥`, () =>
      assert.ok(
        h.calls.filter(
          (c) => c.method === 'GET' && c.path === '/evaluations/eval-fixture-1',
        ).length >= 3,
      ),
    )
    assert.deepEqual(h.errors, [])
    if (mode === 'pending') {
      await h.page
        .getByRole('link', { name: '返回任务列表', exact: true })
        .click()
      await h.page.getByRole('link', { name: '创建评估', exact: true }).click()
      await h.page
        .getByRole('combobox', { name: 'API 密钥', exact: true })
        .waitFor()
      report.assertions.push({
        name: '取消现有任务后同会话仍能创建新任务',
        pass: true,
      })
    }
    await h.context.close()
  }
}

async function progressScenario() {
  report.real.push('evaluation detail live progress (WS + HTTP truth)')
  const {
    page,
    wsUrls,
    detailIntervals,
    detailProgress,
    waitForInitialProgressReconciliation,
    advanceProgress,
    denyProgress,
  } = await fixture('progress', '/evaluations/eval-fixture-1')
  await check('WS 连接 URL 不含 token', async () => {
    await page.waitForSelector('text=实时进度已连接')
    assert.ok(wsUrls.length >= 1, '已发起 WS 连接')
    for (const url of wsUrls) assert.ok(!url.includes('token='), url)
  })
  await waitForInitialProgressReconciliation()
  await page.getByText('20%').first().waitFor()
  const initialRequests = detailIntervals.length
  const eventSentAt = Date.now()
  check('进度事件前呈现 HTTP 初始真值20%', () => assert.ok(true))
  advanceProgress()
  await check('服务端事件触发 HTTP 真值刷新到 60%', async () => {
    await page.getByText('60%').first().waitFor({ timeout: 5_000 })
    assert.ok(detailIntervals.length > initialRequests)
    assert.ok(detailIntervals.at(-1)[0] >= eventSentAt)
    assert.equal(detailProgress.at(-1), 60)
  })
  report.progress_evidence = {
    event_percentage: 50,
    initial_http_percentage: 20,
    final_http_percentage: 60,
    detail_intervals: detailIntervals,
    socket_paths: wsUrls.map((url) => new URL(url, base).pathname),
    http_values: detailProgress,
    reconciliations_before_progress: initialRequests,
  }
  await check('详情请求区间两两不重叠（无并发观察周期）', () => {
    assert.ok(detailIntervals.length >= 2, '已有多次详情请求')
    for (let i = 1; i < detailIntervals.length; i += 1) {
      assert.ok(
        detailIntervals[i][0] >= detailIntervals[i - 1][1],
        `第 ${i} 次请求与上一次重叠`,
      )
    }
  })
  await page.screenshot({ path: resolve(out, 'progress.png'), fullPage: true })
  report.screenshots.push('progress.png')
  await denyProgress()
  await page
    .getByRole('region', { name: '评估详情', exact: true })
    .getByText('model-a', { exact: true })
    .waitFor({ state: 'hidden', timeout: 5000 })
  const remainingActions = await page
    .getByRole('button', { name: '取消任务', exact: true })
    .count()
  check('WS4403清除已显示详情及动作', () => assert.equal(remainingActions, 0))
  await page.screenshot({
    path: resolve(out, 'progress-denied.png'),
    fullPage: true,
  })
  report.screenshots.push('progress-denied.png')
  await page.getByRole('button', { name: '刷新任务', exact: true }).click()
  await page
    .getByText('实时进度已连接', { exact: true })
    .waitFor({ timeout: 5000 })
  await waitForInitialProgressReconciliation()
  const restoredRequests = detailIntervals.length
  const restoredEventAt = Date.now()
  advanceProgress(80)
  await page.getByText('80%').first().waitFor({ timeout: 5000 })
  check('WS4403显式重试恢复订阅且后续事件继续刷新HTTP真值', () => {
    assert.ok(wsUrls.length >= 2)
    assert.ok(detailIntervals.length > restoredRequests)
    assert.ok(detailIntervals.at(-1)[0] >= restoredEventAt)
    assert.equal(detailProgress.at(-1), 80)
  })
}

async function resultsScenario() {
  report.real.push('results list/detail pages and joint task/result observer')
  const h = await fixture('results', '/results')
  await h.page
    .getByRole('table', { name: '评估结果列表', exact: true })
    .waitFor({ timeout: 5000 })
  await check(
    '真实结果列表首屏20行、run_id为空仍有evaluation链接、未知状态可读',
    async () => {
      assert.equal(
        await h.page
          .locator('table[aria-label="评估结果列表"] tbody tr')
          .count(),
        20,
      )
      assert.equal(
        await h.page
          .getByRole('link', { name: 'eval-fixture-1', exact: true })
          .getAttribute('href'),
        '/results/eval-fixture-1',
      )
      await h.page
        .getByText('未知状态（future-result）', { exact: true })
        .waitFor()
    },
  )
  await h.page.getByRole('button', { name: '下一页结果', exact: true }).click()
  await h.page
    .getByRole('link', { name: 'eval-result-21', exact: true })
    .waitFor()
  await check('结果列表分页进入URL', () =>
    assert.equal(new URL(h.page.url()).searchParams.get('offset'), '20'),
  )
  await choose(h.page, '结果状态', '已完成')
  await h.page
    .getByRole('link', { name: 'eval-fixture-1', exact: true })
    .waitFor()
  await check('结果状态筛选清零offset且服务端使用status', () => {
    const query = new URL(h.page.url()).searchParams
    assert.equal(query.get('status'), 'completed')
    assert.equal(query.get('offset'), '0')
    assert.ok(
      h.calls.some(
        (c) => c.path === '/results' && c.query.includes('status=completed'),
      ),
    )
  })
  await h.page.reload()
  await h.page
    .getByRole('link', { name: 'eval-fixture-1', exact: true })
    .click()
  await h.page
    .getByRole('heading', { name: '评估结果详情', exact: true })
    .waitFor()
  await h.page.getByRole('table', { name: '策略汇总', exact: true }).waitFor()
  const strategies = h.page.getByRole('table', {
    name: '策略汇总',
    exact: true,
  })
  const units = h.page.getByRole('table', { name: '单题结果', exact: true })
  const summary = await strategies.innerText()
  await check('全量策略汇总保留百分率、秒、未知成本和难度统计', () => {
    for (const text of [
      '50%',
      '75%',
      '1.25 秒',
      '12',
      '成本未知',
      '0.12 USD',
      'easy',
    ])
      assert.ok(summary.includes(text), text)
  })
  const rows = units.locator('tbody tr')
  await check('单题真实状态与null/零指标、同题多策略均保留', async () => {
    assert.equal(await rows.count(), 20)
    assert.equal(
      await units
        .getByRole('cell', { name: 'result-problem-1', exact: true })
        .count(),
      2,
    )
    const first = await rows.first().innerText()
    assert.ok(first.includes('未知'))
    assert.ok(first.includes('success'))
    assert.ok((await units.innerText()).includes('timeout'))
    assert.ok((await units.innerText()).includes('future-unit'))
    assert.ok((await rows.nth(1).innerText()).includes('1.25 秒'))
  })
  await h.page.getByRole('button', { name: '下一页单题', exact: true }).click()
  await units
    .getByRole('cell', { name: 'result-problem-12', exact: true })
    .first()
    .waitFor()
  await check('单题分页不截断全量汇总且URL保留当前页', async () => {
    assert.equal(await rows.count(), 4)
    assert.equal(await strategies.innerText(), summary)
    assert.equal(new URL(h.page.url()).searchParams.get('offset'), '20')
  })
  await h.page.reload()
  await units
    .getByRole('cell', { name: 'result-problem-12', exact: true })
    .first()
    .waitFor()
  await check('run_id=null的详情可直接访问与刷新分页', () =>
    assert.ok(
      h.calls.some(
        (c) =>
          c.path === '/results/eval-fixture-1' && c.query.includes('offset=20'),
      ),
    ),
  )
  for (const width of [390, 1440]) {
    await h.page.setViewportSize({ width, height: 1000 })
    await h.page.screenshot({
      path: resolve(out, `results-${width}.png`),
      fullPage: true,
    })
    report.screenshots.push(`results-${width}.png`)
    await check(`结果详情${width}px根页面不横向溢出`, async () =>
      assert.ok(
        await h.page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ),
    )
  }
  h.holdResult(0)
  await h.page.getByRole('button', { name: '上一页单题', exact: true }).click()
  await h.waitForHeldResult()
  await h.page.goBack()
  await units
    .getByRole('cell', { name: 'result-problem-12', exact: true })
    .first()
    .waitFor()
  h.releaseResult()
  await h.page.waitForTimeout(250)
  await check('迟到旧分页不能覆盖后退恢复的结果页', async () => {
    assert.equal(new URL(h.page.url()).searchParams.get('offset'), '20')
    assert.equal(await rows.count(), 4)
    assert.equal(
      await units
        .getByRole('cell', { name: 'result-problem-1', exact: true })
        .count(),
      0,
    )
  })
  h.failResult(503)
  await h.page.getByRole('button', { name: '刷新结果', exact: true }).click()
  await h.page.getByRole('alert').waitFor()
  await h.page
    .getByRole('region', { name: '任务信息', exact: true })
    .getByText('model-a', { exact: true })
    .waitFor()
  await check('结果失败保留任务事实而非伪造空结果', async () =>
    assert.equal(await units.count(), 0),
  )
  h.failResult(0)
  await h.page.getByRole('button', { name: '刷新结果', exact: true }).click()
  await units.waitFor()
  h.failDetail(403)
  await h.page.getByRole('button', { name: '刷新结果', exact: true }).click()
  await units.waitFor({ state: 'hidden' })
  await check('任务权限拒绝清除旧结果', async () =>
    assert.equal(await strategies.count(), 0),
  )
  await h.context.close()
  const empty = await fixture('results-empty', '/results')
  await empty.page.getByText('还没有评估结果', { exact: true }).waitFor()
  await check('合法空列表区别于请求错误', () =>
    assert.deepEqual(empty.errors, []),
  )
  empty.failResultsList(true)
  await empty.page.reload()
  await empty.page.getByRole('alert').waitFor()
  empty.failResultsList(false)
  await empty.page.getByRole('button', { name: /^重\s*试$/ }).click()
  await empty.page.getByText('还没有评估结果', { exact: true }).waitFor()
  await check('结果列表失败重试恢复', () => assert.deepEqual(empty.errors, []))
  await empty.context.close()
  const live = await fixture('results-live', '/results/eval-fixture-1')
  await live.page.getByText('实时进度已连接', { exact: true }).waitFor()
  await live.waitForInitialProgressReconciliation()
  const settleDeadline = Date.now() + 5000
  while (live.resultIntervals.length < live.detailIntervals.length) {
    if (Date.now() > settleDeadline)
      throw new Error('Initial joint result cycle did not finish')
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  const baselineTask = live.detailIntervals.length,
    baselineResult = live.resultIntervals.length
  const sentAt = Date.now()
  for (let i = 0; i < 3; i += 1) live.advanceProgress()
  await live.page.getByText('60%').first().waitFor({ timeout: 5000 })
  await live.page
    .getByRole('table', { name: '策略汇总', exact: true })
    .getByRole('cell', { name: '300', exact: true })
    .first()
    .waitFor()
  await check('事件合并后同周期并发读取任务与结果，周期不重叠', () => {
    const tasks = live.detailIntervals.slice(baselineTask),
      results = live.resultIntervals.slice(baselineResult)
    assert.equal(tasks.length, 1)
    assert.equal(results.length, 1)
    assert.ok(tasks[0][0] >= sentAt)
    assert.ok(results[0][0] >= sentAt)
    assert.ok(
      Math.max(tasks[0][0], results[0][0]) <
        Math.min(tasks[0][1], results[0][1]),
    )
  })
  report.results_evidence = {
    task_intervals: live.detailIntervals.map((pair) => [...pair]),
    result_intervals: live.resultIntervals.map((pair) => [...pair]),
    event_sent_at: sentAt,
    baseline_task: baselineTask,
    baseline_result: baselineResult,
    ws_burst_size: 3,
    observed_http_percentage: 60,
    observed_result_avg_tokens: 300,
  }
  await live.denyProgress()
  await live.page
    .getByRole('table', { name: '策略汇总', exact: true })
    .waitFor({ state: 'hidden' })
  await live.page.getByRole('button', { name: '刷新结果', exact: true }).click()
  await live.page.getByText('实时进度已连接', { exact: true }).waitFor()
  await live.page
    .getByRole('table', { name: '策略汇总', exact: true })
    .waitFor()
  await check('WS4403清除结果且显式重试恢复观察', () =>
    assert.ok(live.wsUrls.length >= 2),
  )
  await check('结果页面无运行异常或写请求', () => {
    assert.deepEqual(h.errors, [])
    assert.deepEqual(live.errors, [])
    assert.ok(!h.calls.some((c) => c.method === 'POST'))
  })
  await live.context.close()
}

try {
  if (scenario === 'all' || scenario === 'create') await createScenario()
  if (['all', 'create', 'security'].includes(scenario)) await securityScenario()
  if (scenario === 'all' || scenario === 'list') await listScenario()
  if (scenario === 'all' || scenario === 'detail') await detailScenario()
  if (scenario === 'all' || scenario === 'progress') await progressScenario()
  if (scenario === 'all' || scenario === 'results') await resultsScenario()
  if (
    ![
      'all',
      'create',
      'security',
      'list',
      'detail',
      'progress',
      'results',
    ].includes(scenario)
  )
    throw new Error(`Scenario ${scenario} 尚未实现`)
  await check('无未声明 API 请求', () => assert.deepEqual(report.unknown, []))
  assert.ok(
    report.assertions.every((entry) => entry.pass),
    'Fixture contains failed or pending assertions',
  )
  report.pass = true
} catch (error) {
  report.pass = false
  report.failure = { message: error.message, stack: error.stack }
  console.error(error)
  process.exitCode = 1
} finally {
  await writeFile(
    resolve(out, `${scenario}.json`),
    JSON.stringify(report, null, 2),
  )
  console.log(
    JSON.stringify({
      scenario,
      pass: report.pass,
      assertions: report.assertions.length,
      report: resolve(out, `${scenario}.json`),
    }),
  )
  await browser.close()
}
