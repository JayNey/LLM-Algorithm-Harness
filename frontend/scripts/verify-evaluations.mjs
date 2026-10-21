/* global document, localStorage, window, fetch, setTimeout, getComputedStyle */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
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
    'HTTP /api/v1/users/me',
    'HTTP /api/v1/api-keys',
    'HTTP /api/v1/evaluation-options and children',
    'HTTP /api/v1/evaluations create/start/get',
    'localStorage session marker (no credentials)',
    'security only: isolated HTML and in-memory auth/HTTP transport',
  ],
  real: [
    'React StrictMode',
    'router',
    'session provider',
    'creation store',
    'evaluation client',
    'creation/detail pages',
  ],
}
function check(name, fn) {
  fn()
  report.assertions.push({ name, pass: true })
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
async function fixture(mode = 'start-error') {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  const errors = []
  const calls = []
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
    if (method === 'POST' && path === '/evaluations/eval-fixture-1/start')
      return route.fulfill({
        status: 503,
        headers,
        json: { message: '启动服务暂时不可用' },
      })
    if (method === 'GET' && path === '/evaluations/eval-fixture-1')
      return send(evaluation)
    report.unknown.push(call)
    return route.fulfill({
      status: 599,
      headers,
      json: { message: `Unexpected API: ${method} ${path}` },
    })
  })
  await page.goto(`${base}/evaluations/new`)
  await page.locator('h1').waitFor()
  check('创建地址显示真实创建表单', () =>
    assert.equal(new URL(page.url()).pathname, '/evaluations/new'),
  )
  await page.getByRole('heading', { name: '创建评估', exact: true }).waitFor()
  return { context, page, calls, errors }
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

try {
  if (scenario === 'all' || scenario === 'create') await createScenario()
  if (['all', 'create', 'security'].includes(scenario)) await securityScenario()
  if (!['all', 'create', 'security'].includes(scenario))
    throw new Error(`Scenario ${scenario} 尚未实现`)
  check('无未声明 API 请求', () => assert.deepEqual(report.unknown, []))
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
