/* global localStorage */
// 题目管理页验证（issue #163）——浏览器 fixture 层。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import { Buffer } from 'node:buffer'
import process from 'node:process'
import { emptyNotificationPage } from './fixtures/notifications.mjs'
import console from 'node:console'

const require = createRequire(import.meta.url)
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.PROBLEM_BASE_URL || 'http://127.0.0.1:5180'
const outDir =
  process.env.PROBLEM_QA_DIR ||
  resolve(process.cwd(), '../docs/superpowers/reports/assets/problems/fixture')

const known = [
  'list',
  'import',
  'import-recovery',
  'leetcode',
  'history',
  'all',
]
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

const recoveredProblem = {
  problem_id: 'mine-recovered',
  title: '恢复导入的题目',
  difficulty: null,
  source: 'personal',
}

const leetcodeProblem = {
  problem_id: 'leetcode-1',
  title: 'Two Sum',
  difficulty: 'easy',
  source: 'personal',
}

function historyEntry(problemId, runId, status = 'success') {
  return {
    problem_id: problemId,
    strategy: 'direct',
    status,
    iterations: null,
    tokens: null,
    execution_time: null,
    run_id: runId,
  }
}

function mockRoute(context, job) {
  context.route('**/api/v1/**', (route, request) => {
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    const cors = {
      'access-control-allow-origin': new URL(base).origin,
      'access-control-allow-credentials': 'true',
    }
    if (method === 'OPTIONS')
      return route.fulfill({
        status: 204,
        headers: {
          ...cors,
          'access-control-allow-headers': 'content-type,x-csrf-token',
          'access-control-allow-methods': 'GET,POST,OPTIONS',
        },
      })
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
          {
            id: 'personal',
            label: '个人题目',
            problem_count:
              1 + Number(job.status === 'completed') + Number(!!job.leetcode),
          },
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
      if (job.status === 'completed') personal.push(recoveredProblem)
      if (job.leetcode) personal.push(leetcodeProblem)
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
    if (method === 'POST' && path === '/files/upload')
      return reply({
        file: { id: 'f-import-large', filename: 'large.json', size: 5_242_881 },
        parsed: null,
      })
    if (method === 'POST' && path === '/problems/import/leetcode') {
      assert.deepEqual(request.postDataJSON(), {
        url: 'https://leetcode.com/problems/two-sum/',
      })
      return job.finishLeetcode.then(() => {
        if (job.leetcodeError) return reply(null, job.leetcodeError)
        const imported = !job.leetcode
        job.leetcode = true
        return reply({ problem_id: 'leetcode-1', imported })
      })
    }
    if (method === 'GET' && path === '/problems/personal/leetcode-1')
      return reply({
        description: 'Return indices of the two numbers.',
        source_url: 'https://leetcode.com/problems/two-sum/',
        needs_manual_completion: true,
      })
    if (method === 'POST' && path === '/problems/import') {
      job.status = job.nextStartStatus
      return reply({
        job_id: 'j-import-large',
        task_id: 'task-import-large',
        status: job.status,
      })
    }
    if (method === 'GET' && path === '/imports/j-import-large') {
      if (job.failures > 0) {
        job.failures -= 1
        return reply(null, 503)
      }
      const completed = job.status === 'completed'
      const result = completed
        ? {
            total: 1,
            valid: 1,
            invalid: 0,
            duplicates: 0,
            imported: 1,
            dataset_total: 2,
            errors: [],
            errors_truncated: false,
            file_id: 'f-import-large',
          }
        : job.status === 'failed'
          ? { status_code: 422, detail: '导入 fixture 数据无效' }
          : null
      return reply({
        job_id: 'j-import-large',
        status: job.status,
        processed: completed ? 1 : 0,
        total: 1,
        percentage: completed ? 100 : 0,
        result,
      })
    }
    if (method === 'POST' && path === '/problems/upload')
      return reply({
        file_id: 'f-import-1',
        job_id: 'j-import-1',
        validation: {
          total: 3,
          valid: 2,
          invalid: 1,
          errors: [
            {
              index: 1,
              errors: [{ field: 'description', type: 'missing' }],
            },
          ],
          errors_truncated: false,
          file_id: 'f-import-1',
          duplicates: 1,
          imported: 2,
          dataset_total: 4,
        },
      })
    if (method === 'GET' && path === '/results/problems/mine-1') {
      const offset = Number(url.searchParams.get('offset'))
      if (offset === 20)
        return reply({
          items: [historyEntry('mine-1', 'r-page-2')],
          total: 21,
          limit: 20,
          offset,
          has_more: false,
        })
      return reply({
        items: Array.from({ length: 20 }, (_, index) =>
          index % 2 === 0
            ? historyEntry('mine-1', `r${index}`)
            : historyEntry('mine-1', null, 'error'),
        ),
        total: 21,
        limit: 20,
        offset,
        has_more: true,
      })
    }
    if (method === 'GET' && path === '/results/problems/shared-1') {
      const offset = Number(url.searchParams.get('offset'))
      return reply({
        items: offset === 0 ? [historyEntry('shared-1', 'r-shared-1')] : [],
        total: 1,
        limit: 20,
        offset,
        has_more: false,
      })
    }
    if (method === 'GET' && path === '/results/problems/shared-2')
      return reply({
        items: [],
        total: 0,
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
    await page.getByRole('combobox', { name: '题目来源' }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('个人题目（1）', { exact: true })
      .click()
    const table = page.getByRole('table', { name: '题目列表' })
    await table
      .getByRole('row', { name: /shared-1/ })
      .waitFor({ state: 'hidden' })
    await table.getByRole('row', { name: /mine-1/ }).waitFor()
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
    await page.getByRole('combobox', { name: '导入模式' }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('追加（跳过重复题目）', { exact: true })
      .click()
    await page.getByRole('button', { name: '开始导入' }).click()
    const report = page.getByRole('status', { name: '导入报告' })
    await report.waitFor()
    assert.match(await report.innerText(), /无效\s*1/)
    assert.match(await report.innerText(), /重复\s*1/)
    assert.match(
      await report.getByRole('listitem').innerText(),
      /第\s*2\s*条：description（missing）/,
    )
  })
  await page.screenshot({ path: resolve(outDir, 'import.png'), fullPage: true })
  report.screenshots.push('import.png')
}

async function leetcodeScenario(page, job) {
  await page.goto(`${base}/problems?source=personal&import=1`)
  const input = page.getByRole('textbox', { name: 'LeetCode 题目链接' })
  const submit = page.getByRole('button', { name: '导入链接' })
  await check('链接导入等待并锁定提交，完成后刷新个人题库', async () => {
    let finish
    job.finishLeetcode = new Promise((resolve) => {
      finish = resolve
    })
    try {
      await input.fill('https://leetcode.com/problems/two-sum/', {
        timeout: 6_000,
      })
      await submit.click()
      await page
        .getByRole('status')
        .filter({ hasText: '正在从 LeetCode 导入' })
        .waitFor()
      assert.ok(await submit.isDisabled())
      assert.ok(
        await page.getByRole('button', { name: '开始导入' }).isDisabled(),
      )
    } finally {
      finish()
    }
    await page.getByText('已导入个人题库。').waitFor()
    await page.getByRole('row', { name: /Two Sum/ }).waitFor()
    await page.getByRole('combobox', { name: '题目来源' }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('个人题目（2）', { exact: true })
      .waitFor()
    await page.keyboard.press('Escape')
  })
  await check('个人题目详情展示 LeetCode 来源和补全状态', async () => {
    await page
      .getByRole('row', { name: /Two Sum/ })
      .getByRole('button', { name: '题目详情' })
      .click()
    const dialog = page.getByRole('dialog', { name: /Two Sum/ })
    await dialog.getByText('Return indices of the two numbers.').waitFor()
    const link = dialog.getByRole('link', { name: '在 LeetCode 查看原题' })
    assert.equal(
      await link.getAttribute('href'),
      'https://leetcode.com/problems/two-sum/',
    )
    assert.ok(
      await dialog.getByText('公开样例或 Python 入口需人工补全。').isVisible(),
    )
    await page.screenshot({
      path: resolve(outDir, 'leetcode.png'),
      animations: 'disabled',
    })
    report.screenshots.push('leetcode.png')
    await page.keyboard.press('Escape')
  })
  await check('重复和超时分别提示，保留已导入题目', async () => {
    await input.fill('https://leetcode.com/problems/two-sum/')
    await submit.click()
    await page.getByText('题目已存在，已跳过。').waitFor()
    job.leetcodeError = 408
    await submit.click()
    await page
      .getByRole('alert')
      .filter({ hasText: 'LeetCode 请求超时' })
      .waitFor()
    assert.equal(await page.getByRole('row', { name: /Two Sum/ }).count(), 1)
  })
}

async function importRecoveryScenario(page, job) {
  const progressPath = '/imports/j-import-large'
  const progressRequest = () =>
    page.waitForRequest((request) => request.url().endsWith(progressPath), {
      timeout: 6_000,
    })
  const openImport = () =>
    page
      .getByRole('main')
      .getByRole('button', { name: '导入题目', exact: true })
      .click()
  const selectFile = () =>
    page.setInputFiles('input[type="file"]', {
      name: 'large.json',
      mimeType: 'application/json',
      buffer: Buffer.alloc(5_242_881),
    })
  const submit = page.getByRole('button', { name: '开始导入' })
  const pollError = page.getByRole('alert').filter({ hasText: '进度查询' })
  const jobRequests = () =>
    report.replaced.filter((request) => request === `GET ${progressPath}`)
      .length
  const setAccount = (marker, username) =>
    page.evaluate(
      ({ marker, username }) =>
        localStorage.setItem(
          'llm-harness-session',
          JSON.stringify({
            marker,
            username,
            expiresAt: Date.now() + 3_600_000,
          }),
        ),
      { marker, username },
    )

  await page.goto(`${base}/problems`)
  await openImport()
  job.failures = 3
  await selectFile()
  await submit.click()

  await check('连续三次失败后硬刷新查询同一作业且锁定提交', async () => {
    await pollError.waitFor({ timeout: 15_000 })
    assert.equal(jobRequests(), 3)
    assert.ok(await submit.isDisabled())
    await Promise.all([progressRequest(), page.reload()])
    await selectFile()
    assert.ok(await submit.isDisabled())
  })

  await check('再次中断时手动重试原作业并展示暂停状态', async () => {
    job.failures = 3
    await pollError.waitFor({ timeout: 15_000 })
    const retry = page.getByRole('button', { name: '重试查询导入进度' })
    job.status = 'paused'
    await Promise.all([progressRequest(), retry.click({ timeout: 5_000 })])
    await page.getByText(/导入已暂停.*j-import-large/).waitFor()
    assert.ok(await submit.isDisabled())
    assert.equal(
      report.replaced.filter((request) => request === 'POST /files/upload')
        .length,
      1,
    )
    assert.equal(
      report.replaced.filter((request) => request === 'POST /problems/import')
        .length,
      1,
    )
  })

  await check('离开后回到题库继续原作业，另一账号没有旧作业', async () => {
    const navigation = page.getByRole('navigation', { name: '主导航' })
    await navigation.getByRole('link', { name: '帮助文档' }).click()
    await page.waitForURL('**/help')
    await Promise.all([
      progressRequest(),
      navigation.getByRole('link', { name: '题目库' }).click(),
    ])
    await openImport()
    await page.getByText(/导入已暂停.*j-import-large/).waitFor()
    const beforeSwitch = jobRequests()
    await setAccount('fixture-other', 'other')
    await page.reload()
    await selectFile()
    assert.ok(await submit.isEnabled())
    assert.equal(await page.getByText(/j-import-large/).count(), 0)
    await assert.rejects(progressRequest(), { name: 'TimeoutError' })
    assert.equal(jobRequests(), beforeSwitch)
  })

  await check('原会话恢复后显示原作业报告并刷新列表及来源计数', async () => {
    await setAccount('fixture-user', 'fixture')
    await Promise.all([progressRequest(), page.reload()])
    await page.getByText(/导入已暂停.*j-import-large/).waitFor()
    await page.getByRole('combobox', { name: '题目来源' }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('个人题目（1）', { exact: true })
      .waitFor()
    await page.keyboard.press('Escape')
    job.status = 'completed'
    const result = page.getByRole('status', { name: '导入报告' })
    await result.waitFor({ timeout: 10_000 })
    assert.match(await result.innerText(), /库存量\s*2/)
    await page.getByRole('row', { name: /mine-recovered/ }).waitFor()
    await page.getByRole('combobox', { name: '题目来源' }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('个人题目（2）', { exact: true })
      .waitFor()
    await page.keyboard.press('Escape')
  })

  await check('触发接口直接返回失败时查询终态详情并解锁', async () => {
    job.nextStartStatus = 'failed'
    await selectFile()
    await Promise.all([progressRequest(), submit.click()])
    await page
      .getByRole('alert')
      .filter({ hasText: '导入 fixture 数据无效' })
      .waitFor()
    assert.ok(await submit.isEnabled())
  })
}

async function historyScenario(page) {
  await page.goto(`${base}/problems`)
  const openHistory = (problemId) =>
    page
      .getByRole('row', { name: new RegExp(problemId) })
      .getByRole('button', { name: '评估历史' })
      .click()
  const closeHistory = async (dialog) => {
    await dialog.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
  }
  const historyRequest = (problemId) =>
    page.waitForRequest(
      (request) =>
        new URL(request.url()).pathname ===
        `/api/v1/results/problems/${problemId}`,
    )
  const personal = page.getByRole('dialog', { name: /个人题一.*评估历史/ })
  const shared = page.getByRole('dialog', { name: /共享题一.*评估历史/ })
  const table = personal.getByRole('table', { name: '题目评估历史' })
  await check('评估历史抽屉聚合', async () => {
    await openHistory('mine-1')
    await table.waitFor()
    assert.match(await personal.getByRole('status').innerText(), /通过率\s*50%/)
    assert.equal(
      await table.getByRole('cell', { name: '执行错误' }).count(),
      10,
    )
  })
  await page.screenshot({
    path: resolve(outDir, 'history.png'),
    fullPage: true,
  })
  report.screenshots.push('history.png')

  await check('同一题目的下一页显示对应记录', async () => {
    await personal.getByRole('button', { name: '下一页' }).click()
    await table.getByRole('cell', { name: 'r-page-2' }).waitFor()
  })
  await check('换题后的首个历史请求从首页开始', async () => {
    await closeHistory(personal)
    const [request] = await Promise.all([
      historyRequest('shared-1'),
      openHistory('shared-1'),
    ])
    assert.equal(new URL(request.url()).searchParams.get('offset'), '0')
    await shared.getByRole('cell', { name: 'r-shared-1' }).waitFor()
    await closeHistory(shared)
  })
  await check('旧题的迟到响应不会覆盖当前题目', async () => {
    const delayed = Promise.withResolvers()
    const intercepted = Promise.withResolvers()
    const path = '**/results/problems/mine-1?*'
    await page.route(path, async (route) => {
      intercepted.resolve()
      await delayed.promise
      await route.fallback()
    })
    try {
      const [oldRequest] = await Promise.all([
        historyRequest('mine-1'),
        openHistory('mine-1'),
        intercepted.promise,
      ])
      await closeHistory(personal)
      await openHistory('shared-1')
      const currentRecord = shared.getByRole('cell', { name: 'r-shared-1' })
      await currentRecord.waitFor()
      delayed.resolve()
      const response = await oldRequest.response()
      await response?.finished()
      assert.ok(await currentRecord.isVisible())
      assert.equal(
        await shared.getByRole('cell', { name: 'r0', exact: true }).count(),
        0,
      )
      await closeHistory(shared)
    } finally {
      delayed.resolve()
      await page.unroute(path)
    }
  })
  await check('无历史记录的题目显示真实空态', async () => {
    await openHistory('shared-2')
    await page
      .getByRole('dialog', { name: /共享题二.*评估历史/ })
      .getByText('该题还没有评估记录。')
      .waitFor()
  })
}

const { chromium } = playwright
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
try {
  const context = await browser.newContext()
  await context.addInitScript(() => {
    if (localStorage.getItem('llm-harness-session')) return
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'fixture-user',
        username: 'fixture',
        expiresAt: Date.now() + 3_600_000,
      }),
    )
  })
  const job = { status: null, nextStartStatus: 'running', failures: 0 }
  mockRoute(context, job)
  const page = await context.newPage()
  if (scenario === 'all' || scenario === 'list') await listScenario(page)
  if (scenario === 'all' || scenario === 'import') await importScenario(page)
  if (scenario === 'all' || scenario === 'history') await historyScenario(page)
  if (scenario === 'all' || scenario === 'import-recovery')
    await importRecoveryScenario(page, job)
  if (scenario === 'all' || scenario === 'leetcode')
    await leetcodeScenario(page, job)
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
