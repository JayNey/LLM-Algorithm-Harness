/* global document, getComputedStyle, localStorage */
// 响应式与键盘焦点验收（issue #446）——生产构建（vite preview）+ fixture 层。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import process from 'node:process'
import { emptyNotificationPage } from './fixtures/notifications.mjs'
import console from 'node:console'

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.RESPONSIVE_BASE_URL || 'http://127.0.0.1:5194'
const outDir =
  process.env.RESPONSIVE_QA_DIR ||
  resolve(process.cwd(), '../docs/frontend/assets/v06')
const scenario = process.argv[2] || 'all'
const known = ['responsive', 'keyboard', 'forms', 'all']
assert.ok(known.includes(scenario), `未知场景：${scenario}`)

const report = {
  scenario,
  layer: 'browser-fixture over production build (not backend E2E)',
  assertions: [],
  replaced: [],
  unknown: [],
  screenshots: [],
  coverage: { viewports: [], combos: [], uncovered: [] },
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
        throw error
      },
    )
}

const VIEWPORTS = [
  [320, 700],
  [390, 844],
  [768, 1024],
  [1024, 768],
  [1440, 900],
]

// 四个目标页面：题库、设置（预算）、监控（系统状态）、基准历史。
const PAGES = [
  {
    key: 'problems',
    path: '/problems',
    // 锚点双语：zh 原文与 en 译文（en-US 词典）都可能是当前可见文案。
    readyRole: ['button', /评估历史|Evaluation history/],
    op: /评估历史|Evaluation history/,
  },
  {
    key: 'budgets',
    path: '/settings/budgets',
    // antd 会对两个汉字的按钮文本插入空格（“编 辑”），需按正则匹配。
    readyRole: ['button', /编\s*辑|Edit/],
    op: /编\s*辑|Edit/,
  },
  {
    key: 'system',
    path: '/settings/system',
    readyRole: ['heading', /系统状态|System status/],
    op: /立即刷新|Refresh now/,
  },
  {
    key: 'benchmarks',
    path: '/benchmarks/suite',
    readyRole: ['region', /运行历史|Run history/],
    op: /下一页|Next/,
  },
]

async function mockRoute(context, state) {
  await context.route('**/api/v1/**', (route, request) => {
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    const cors = {
      'access-control-allow-origin': new URL(base).origin,
      'access-control-allow-credentials': 'true',
    }
    if (method === 'OPTIONS')
      return route.fulfill({ status: 204, headers: cors })
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        headers: cors,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data, message: '' }),
      })
    report.replaced.push(`${method} ${path}`)
    if (method === 'GET' && path === '/notifications')
      return reply(emptyNotificationPage)
    if (method === 'GET' && path === '/users/me')
      return reply({
        id: 'fixture',
        username: 'fixture-admin',
        role: 'admin',
        email: 'f@e.org',
        created_at: '2026-10-24',
      })
    if (method === 'GET' && path === '/evaluation-options')
      return reply({ strategies: [{ name: 'vanilla' }], sources: [] })
    if (method === 'GET' && path === '/evaluation-options/problems') {
      const items = Array.from({ length: 12 }, (_, i) => ({
        problem_id: `prob-${i + 1}`,
        title: `长标题题目第 ${i + 1} 号：两数之和与三数之和的综合变体`,
        difficulty: i % 3 === 0 ? 'easy' : i % 3 === 1 ? 'medium' : 'hard',
        source: i % 2 === 0 ? 'personal' : 'shared',
      }))
      return reply({
        items,
        total: items.length,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    }
    if (method === 'GET' && path.startsWith('/results/problems/')) {
      const items = Array.from({ length: 8 }, (_, i) => ({
        evaluation_id: `ev-${i + 1}`,
        run_id: `run-${i + 1}`,
        strategy: i % 2 === 0 ? 'vanilla' : 'reflexion',
        model: 'test-model',
        status: i % 4 === 3 ? 'failed' : 'success',
        created_at: '2026-11-01T00:00:00Z',
        completed_at: '2026-11-01T00:01:00Z',
      }))
      return reply({
        items,
        total: items.length,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    }
    if (method === 'GET' && path === '/budgets')
      return reply({
        global_cap_usd: 100,
        difficulty_caps: { easy: 30, medium: null, hard: 20 },
        action: 'pause',
      })
    if (method === 'GET' && path === '/budgets/usage')
      return reply({
        global_budget: {
          cap_usd: 100,
          used_usd: 40,
          remaining_usd: 60,
          percentage_used: 40,
          known_cost_usd: 40,
          cost_complete: true,
          unknown_cost_count: 0,
          unknown_reasons: {},
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
    if (method === 'GET' && path === '/alerts/history')
      return reply([
        {
          id: 'event-1',
          rule_id: 'rule-1',
          threshold_pct: 80,
          used_usd: 40,
          cap_usd: 100,
          channel: 'webhook',
          triggered_at: '2026-10-28T00:00:00Z',
        },
      ])
    if (method === 'GET' && path === '/costs/summary')
      return reply({
        since: null,
        until: null,
        total_cost_usd: 1.25,
        task_count: 2,
        by_source: {
          evaluations: {
            cost_usd: 1.0,
            task_count: 1,
            known_cost_usd: 1.0,
            cost_complete: true,
            unknown_cost_count: 0,
            unknown_reasons: {},
          },
          benchmarks: {
            cost_usd: 0.25,
            task_count: 1,
            known_cost_usd: 0.25,
            cost_complete: true,
            unknown_cost_count: 0,
            unknown_reasons: {},
          },
        },
        known_cost_usd: 1.25,
        cost_complete: true,
        unknown_cost_count: 0,
        unknown_reasons: {},
      })
    if (method === 'GET' && path === '/costs/trends')
      return reply({
        since: null,
        until: null,
        data: [
          {
            date: '2026-10-28',
            cost_usd: 1.25,
            known_cost_usd: 1.25,
            cost_complete: true,
            unknown_cost_count: 0,
            unknown_reasons: {},
          },
        ],
        known_cost_usd: 1.25,
        cost_complete: true,
        unknown_cost_count: 0,
        unknown_reasons: {},
      })
    if (method === 'GET' && path === '/costs/breakdown')
      return reply({
        since: null,
        until: null,
        by_source: { evaluations: 1.0, benchmarks: 0.25 },
        by_model: { 'model-x': 1.25 },
        by_strategy: { vanilla: 1.25 },
        known_cost_usd: 1.25,
        cost_complete: true,
        unknown_cost_count: 0,
        unknown_reasons: {},
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
            sandbox: { status: 'not_checked' },
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
    if (method === 'GET' && path === '/health/sandbox') {
      state.sandboxCalls++
      return reply({ status: 'ok' })
    }
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
        status: 'ok',
        enabled: true,
        total_entries: 20,
        disk_usage_mb: 1.5,
        hit_rate: 0.6,
        hits: 12,
        misses: 8,
        api_calls_saved: 12,
      })
    if (method === 'GET' && path === '/config/sandbox')
      return reply({
        backend: 'docker',
        docker_image: 'harness-sandbox:latest',
        timeout_seconds: 30,
        memory_limit_mb: 512,
        max_output_bytes: 65536,
        max_processes: 64,
        allowed_imports: ['json', 'math'],
      })
    if (method === 'GET' && path === '/config/strategies')
      return reply({
        strategies: [
          { name: 'vanilla', defaults: { temperature: 0.7 } },
          { name: 'self_consistency', defaults: { samples: 5 } },
        ],
      })
    if (method === 'GET' && path === '/config/providers')
      return reply({
        status: 'ok',
        live_provider_availability_checked: false,
        providers: [
          { provider: 'openai', models: ['gpt-test'] },
          { provider: 'deepseek', models: ['deepseek-test'] },
        ],
      })
    if (method === 'GET' && path === '/api-keys')
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
    if (method === 'GET' && path === '/datasets') return reply([])
    const benchRow = (id, status = 'completed') => ({
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
    if (method === 'GET' && path === '/benchmarks/suites/suite')
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
    if (method === 'GET' && path === '/benchmarks/suites/suite/runs') {
      const offset = Number(url.searchParams.get('offset') || 0)
      const limit = Number(url.searchParams.get('limit') || 20)
      const all = Array.from({ length: 25 }, (_, i) =>
        benchRow(`history-${i}`, i % 5 === 4 ? 'failed' : 'completed'),
      )
      return reply({
        items: all.slice(offset, offset + limit),
        total: all.length,
        limit,
        offset,
        has_more: offset + limit < all.length,
      })
    }
    if (method === 'GET' && path === '/benchmarks/learning-curve/suite')
      return reply({
        suite_id: 'suite',
        suite_name: 'History suite',
        data: [
          {
            run_id: 'history-0',
            timestamp: '2026-11-01T00:00:00Z',
            model: 'test-model',
            accuracy: 0.5,
            cost_usd: null,
          },
        ],
        trends: { accuracy_growth_rate: null, cost_growth_rate: null },
      })
    if (method === 'GET' && path.startsWith('/benchmarks/runs/')) {
      const id = decodeURIComponent(path.split('/').at(-1))
      return reply(benchRow(id, id === 'active' ? 'running' : 'completed'))
    }
    if (method === 'GET' && path.startsWith('/tasks/')) {
      const id = path.slice('/tasks/'.length)
      return reply({
        id,
        entity_id: id.replace(/^task-/, ''),
        task_type: 'benchmark',
        status: 'running',
        progress: { current: 1, total: 2, percentage: 50, current_step: 'p1' },
        error_message: null,
      })
    }
    report.unknown.push(`${method} ${path}`)
    return reply(null, 404)
  })
}

async function newPage(
  browser,
  { width, height, language = 'zh-CN', scheme = 'light', session = true },
) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.addInitScript(
    ([lang, theme, withSession]) => {
      // 语言只在首次导航播种：语言保持测试需要在 reload 后读用户写入值，
      // initScript 若每次导航都覆写会把语言打回默认。
      if (localStorage.getItem('llm-harness-language-seed') !== '1') {
        localStorage.setItem('llm-harness-language', lang)
        localStorage.setItem('llm-harness-language-seed', '1')
      }
      localStorage.setItem(
        'llm-harness-ui',
        JSON.stringify({
          appearanceVariant: 'orbit',
          themes: { orbit: theme, precision: theme, studio: theme },
          sidebarCollapsed: false,
        }),
      )
      if (withSession)
        localStorage.setItem(
          'llm-harness-session',
          JSON.stringify({
            marker: 'fixture-admin',
            username: 'fixture-admin',
            expiresAt: Date.now() + 3_600_000,
          }),
        )
    },
    [language, scheme, session],
  )
  await mockRoute(context, state)
  const page = await context.newPage()
  return { context, page }
}

const state = { sandboxCalls: 0 }

async function assertNoPageHScroll(page, label) {
  await check(`${label}：无整页横向滚动`, async () => {
    const m = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
    }))
    assert.ok(
      m.sw <= m.cw + 1,
      `整页出现横向滚动 scrollWidth=${m.sw} clientWidth=${m.cw}`,
    )
  })
}

async function assertTablesScrollable(page, label) {
  await check(`${label}：宽表格在自身容器内滚动且不被裁切`, async () => {
    const issues = await page.evaluate(() => {
      const out = []
      const findHost = (table) => {
        let node = table.parentElement
        while (node && node !== document.body) {
          if (node.classList?.contains('evaluation-list-scroll')) return node
          const ox = getComputedStyle(node).overflowX
          if (ox === 'auto' || ox === 'scroll') return node
          node = node.parentElement
        }
        return null
      }
      for (const table of document.querySelectorAll(
        'table.evaluation-list-table',
      )) {
        if (!table.getClientRects().length) continue
        const name = table.getAttribute('aria-label') ?? '(无标签)'
        const host = findHost(table)
        if (!host) {
          out.push(`${name}: 缺少滚动容器`)
          continue
        }
        const hostBox = host.getBoundingClientRect()
        const tableBox = table.getBoundingClientRect()
        if (hostBox.width > 0 && tableBox.width > hostBox.width + 1) {
          const scrollable = host.scrollWidth >= tableBox.width - 1
          if (!scrollable) out.push(`${name}: 容器不可滚动到表格末尾`)
        }
      }
      return out
    })
    assert.deepEqual(issues, [], `表格滚动容器问题：${issues.join('；')}`)
  })
}

async function assertKeyOpReachable(page, label, op) {
  await check(`${label}：关键操作「${op}」可达`, async () => {
    const control = page.getByRole('button', { name: op }).first()
    await control.waitFor({ state: 'attached' })
    await control.scrollIntoViewIfNeeded()
    const box = await control.boundingBox()
    assert.ok(box, `「${op}」无可见几何框`)
  })
}

async function responsiveScenario(browser) {
  for (const [width, height] of VIEWPORTS) {
    for (const target of PAGES) {
      // 语言与外观覆盖：390px 档以英文+深色运行一页，其余 zh+浅色。
      const variant =
        width === 390
          ? { language: 'en-US', scheme: 'dark' }
          : { language: 'zh-CN', scheme: 'light' }
      report.coverage.combos.push(
        `${target.key}@${width}px/${variant.language}/${variant.scheme}`,
      )
      const { context, page } = await newPage(browser, {
        width,
        height,
        ...variant,
      })
      try {
        await page.goto(`${base}${target.path}`)
        await page
          .getByRole(target.readyRole[0], { name: target.readyRole[1] })
          .first()
          .waitFor({ timeout: 15_000 })
        const label = `${target.key}@${width}px`
        await assertNoPageHScroll(page, label)
        await assertTablesScrollable(page, label)
        await assertKeyOpReachable(page, label, target.op)
        if (
          width === 320 ||
          width === 1440 ||
          (width === 390 && variant.scheme === 'dark')
        ) {
          const shot = `${target.key}-${width}${variant.scheme === 'dark' ? '-dark' : ''}.png`
          await page.screenshot({
            path: resolve(outDir, shot),
            fullPage: false,
          })
          report.screenshots.push(shot)
        }
      } finally {
        await context.close()
      }
    }
  }
  report.coverage.viewports = VIEWPORTS.map(([w]) => `${w}px`)
}

async function keyboardScenario(browser) {
  const { context, page } = await newPage(browser, {
    width: 390,
    height: 844,
  })
  try {
    await page.goto(`${base}/benchmarks/suite`)
    await page.getByRole('region', { name: '运行历史' }).waitFor()

    await check(
      '跳转正文链接是首个停靠点，聚焦即入视口且 Enter 生效',
      async () => {
        // 路由切换会程序化聚焦 main（无障碍设计），顺序导航起点随之前移，
        // 故此处验证 skip-link 的结构性契约而非固定首 Tab：
        // 1) 它是文档中第一个可见可聚焦元素；
        // 2) 聚焦后进入视口（CSS :focus 位移）；
        // 3) Enter 触发后焦点进入主内容。
        const first = await page.evaluate(() => {
          const tabbables = [
            ...document.querySelectorAll(
              'a[href],button,select,input,textarea,[tabindex="0"]',
            ),
          ].filter((el) => el.getClientRects().length > 0)
          const el = tabbables[0]
          return el ? `${el.tagName}.${el.className}` : ''
        })
        assert.match(first, /skip-link/)
        const visible = await page.evaluate(() => {
          const skip = document.querySelector('.skip-link')
          skip?.focus()
          const box = skip?.getBoundingClientRect()
          return Boolean(box && box.bottom > 0 && box.top >= 0)
        })
        assert.ok(visible, '聚焦后 skip-link 未进入视口')
        await page.keyboard.press('Enter')
        const inMain = await page.evaluate(
          () => document.activeElement?.tagName === 'MAIN',
        )
        assert.ok(inMain, 'Enter 后焦点未进入主内容')
      },
    )

    await check('通知抽屉 Esc 关闭后焦点回到触发按钮', async () => {
      const trigger = page.getByRole('button', { name: /通知中心/ }).first()
      await trigger.click()
      const drawer = page.getByRole('dialog')
      await drawer.waitFor()
      await page.keyboard.press('Escape')
      await drawer.waitFor({ state: 'hidden' })
      const back = await page.evaluate(() => ({
        cls: document.activeElement?.className ?? '',
        expanded: document.activeElement?.getAttribute('aria-expanded'),
      }))
      assert.match(back.cls, /ant-btn|trigger|bell/, `焦点未回归：${back.cls}`)
    })

    await check('分页按钮可键盘到达且 Enter 生效', async () => {
      const next = page.getByRole('button', { name: '下一页' })
      await next.scrollIntoViewIfNeeded()
      let focused = null
      for (let i = 0; i < 80; i++) {
        await page.keyboard.press('Tab')
        const label = await page.evaluate(
          () =>
            document.activeElement?.getAttribute('aria-label') ??
            document.activeElement?.textContent ??
            '',
        )
        if (label.includes('下一页')) {
          focused = true
          break
        }
      }
      assert.ok(focused, 'Tab 遍历 80 步未到达「下一页」')
      await page.keyboard.press('Enter')
      await page.getByText('history-20').first().waitFor()
    })

    await check('表格行操作按钮在滚动容器内可达（评估历史）', async () => {
      await page.setViewportSize({ width: 320, height: 700 })
      await page.goto(`${base}/problems`)
      const op = page.getByRole('button', { name: '评估历史' }).first()
      await op.scrollIntoViewIfNeeded()
      const box = await op.boundingBox()
      assert.ok(box && box.width > 0, '「评估历史」不可见')
      await op.click()
      const dialog = page.getByRole('dialog', { name: /评估历史/ })
      await dialog.waitFor()
      await page.keyboard.press('Escape')
      await dialog.waitFor({ state: 'hidden' })
    })
  } finally {
    await context.close()
  }
}

async function formsScenario(browser) {
  for (const [width, height] of [
    [320, 700],
    [1440, 900],
  ]) {
    for (const language of ['zh-CN', 'en-US']) {
      const { context, page } = await newPage(browser, {
        width,
        height,
        language,
        session: false,
      })
      try {
        await page.goto(`${base}/login`)
        await check(
          `登录表单可访问名称（${width}px/${language}）`,
          async () => {
            const identity = page.getByLabel(
              language === 'zh-CN' ? '用户名或邮箱' : /Username or email/i,
            )
            const password = page.getByLabel(
              language === 'zh-CN' ? '密码' : /Password/i,
            )
            await identity.waitFor()
            await password.waitFor()
          },
        )
        await check(
          `登录空提交显示字段错误且与控件关联（${width}px/${language}）`,
          async () => {
            const item = page.locator('.ant-form-item').filter({
              has: page.getByLabel(
                language === 'zh-CN' ? '用户名或邮箱' : /Username or email/i,
              ),
            })
            // antd 两字按钮会插空格（“登 录”），按正则匹配。
            await page.getByRole('button', { name: /登\s*录|Sign in/i }).click()
            await item.locator('.ant-form-item-explain-error').first().waitFor()
            const invalid = await item
              .locator('input')
              .first()
              .getAttribute('aria-invalid')
            assert.equal(invalid, 'true', '错误字段未标注 aria-invalid')
          },
        )
        await check(
          `应用内切换语言与主题后表单内容与焦点可用（${width}px）`,
          async () => {
            if (language !== 'zh-CN') return // en→zh 对称，跳过重复
            const identity = page.getByLabel('用户名或邮箱')
            await identity.fill('user@example.com')
            // 应用内切换语言（不重载页面）。
            await page
              .getByRole('combobox', { name: /界面语言|Language/i })
              .selectOption('en-US')
            const english = page.getByLabel(/Username or email/i)
            await english.waitFor()
            assert.equal(await english.inputValue(), 'user@example.com')
            // 切换主题（AuthLayout 的深浅切换按钮显示目标主题名）后焦点仍可用。
            await page
              .getByRole('button', { name: /深\s*色|Dark/i })
              .first()
              .click()
            const theme = await page.evaluate(
              () => document.documentElement.dataset.theme,
            )
            assert.equal(theme, 'dark')
            await english.click()
            await english.pressSequentially('-filled')
            assert.equal(
              await english.inputValue(),
              'user@example.com-filled',
              '切换主题后输入焦点不可用',
            )
          },
        )
      } finally {
        await context.close()
      }
    }
  }
  const { context, page } = await newPage(browser, {
    width: 320,
    height: 700,
    scheme: 'dark',
    session: false,
  })
  try {
    await page.goto(`${base}/register`)
    await check('注册表单深色主题下可访问名称齐全', async () => {
      for (const label of [
        /用户名|Username/i,
        /邮箱|Email/i,
        /密码|Password/i,
      ]) {
        await page.getByLabel(label).first().waitFor()
      }
      const theme = await page.evaluate(() => ({
        attr: document.documentElement.dataset.theme,
      }))
      assert.equal(theme.attr, 'dark')
      const shot = 'register-320-dark.png'
      await page.screenshot({ path: resolve(outDir, shot) })
      report.screenshots.push(shot)
    })
  } finally {
    await context.close()
  }
}

const { chromium } = playwright
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
try {
  if (scenario === 'all' || scenario === 'responsive')
    await responsiveScenario(browser)
  if (scenario === 'all' || scenario === 'keyboard')
    await keyboardScenario(browser)
  if (scenario === 'all' || scenario === 'forms') await formsScenario(browser)
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
    `scenario=${scenario} assertions=${report.assertions.length} failed=${failed.length} unknown=${report.unknown.length} screenshots=${report.screenshots.length}`,
  )
  if (failed.length)
    for (const item of failed)
      console.log(`FAILED: ${item.name} :: ${item.error}`)
  await browser.close()
  if (failed.length) process.exitCode = 1
}
