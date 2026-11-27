/* global localStorage */
// From frontend: node --experimental-strip-types scripts/verify-pareto-inputs.mjs
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import process from 'node:process'
import { setTimeout } from 'node:timers/promises'
import { URL } from 'node:url'
import { chromium } from 'playwright'
import { emptyNotificationPage } from './fixtures/notifications.mjs'
const root = resolve(import.meta.dirname, '../..')
const out = process.env.PARETO_QA_DIR || '/tmp/issue-524-qa'
mkdirSync(out, { recursive: true })
const reports = Object.fromEntries(
  ['exp-524', 'exp-second', 'exp-bad', 'exp-other'].map((id) => [
    id,
    {
      experiment: {
        experiment_id: id,
        code_version: { git_commit: 'fixed', git_dirty: false },
        dataset: {
          sha256: id === 'exp-bad' ? 'different' : 'same',
          problem_ids: ['p'],
        },
        sandbox_config: {},
        models: [{ model: 'cheap' }, { model: 'premium' }],
        strategies: [{ name: 'direct' }],
      },
      combinations: [
        ['cheap', 0.01, 1],
        ['premium', 1, 1],
      ].map(([model, cost, solved]) => ({
        model,
        strategy: 'direct',
        solved,
        denominator: { total: 2 },
        cost: { known: true, total_cost_usd: cost },
        formal: { evaluable: 1, solved: model === 'cheap' ? 0 : solved },
      })),
    },
  ]),
)
const python = `
import json, sys
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.ab_tests import router, current_user
app=FastAPI()
app.include_router(router)
app.dependency_overrides[current_user]=lambda: object()
r=TestClient(app).post('/api/v1/pareto/analyze', json=json.load(sys.stdin))
print(json.dumps({'status':r.status_code,'body':r.json()}))
`
function analyze(payload) {
  const r = spawnSync(
    process.env.PARETO_PYTHON || resolve(root, '.venv/bin/python'),
    ['-c', python],
    {
      cwd: root,
      input: JSON.stringify(payload),
      encoding: 'utf8',
      timeout: 20000,
    },
  )
  assert.equal(r.status, 0, r.stderr)
  return JSON.parse(r.stdout.trim().split('\n').at(-1))
}
const fixtureJob = {
  id: 'exp-524',
  name: 'Pareto fixture',
  status: 'completed',
  config: {
    name: 'Pareto fixture',
    dataset_path: 'fixture.json',
    models: [{ model: 'cheap' }],
    strategies: [{ name: 'direct' }],
    repeats: 1,
    budget: null,
    execution: 'serial',
    max_workers: 4,
  },
  error_message: null,
  created_at: '2026-11-26T00:00:00Z',
  updated_at: '2026-11-26T00:00:00Z',
}
const requests = [],
  unknown = []
let listFail = true,
  readFail = false,
  failNext = false,
  delayed = null,
  release
async function eventually(check) {
  for (let i = 0; i < 100; i++) {
    try {
      await check()
      return
    } catch (e) {
      if (i === 99) throw e
    }
    await setTimeout(50)
  }
}
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
try {
  const context = await browser.newContext()
  await context.addInitScript(() =>
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'fixture-user',
        username: 'fixture',
        expiresAt: Date.now() + 3600000,
      }),
    ),
  )
  await context.route('**/api/v1/**', async (route, request) => {
    const url = new URL(request.url()),
      path = url.pathname.replace('/api/v1', '')
    const reply = (data, status = 200, message = '') =>
      route
        .fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify({ success: status === 200, data, message }),
        })
        .catch((e) => {
          if (!/closed|handled|intercept/i.test(String(e))) throw e
        })
    if (path === '/users/me')
      return reply({ id: 'user-524', username: 'fixture', role: 'user' })
    if (path === '/notifications') return reply(emptyNotificationPage)
    if (path === '/experiments') {
      if (listFail) {
        listFail = false
        return reply(null, 500, 'list failed')
      }
      const offset = Number(url.searchParams.get('offset'))
      const ids = offset === 0 ? ['exp-second'] : ['exp-bad']
      return reply({
        items: ids.map((id) => ({ ...fixtureJob, id, name: id })),
        limit: 20,
        offset,
        total: 21,
        has_more: offset === 0,
      })
    }
    if (/^\/experiments\/exp-(524|other)$/.test(path))
      return reply({ ...fixtureJob, id: path.split('/').at(-1) })

    const match = path.match(/^\/experiments\/([^/]+)\/comparison$/)
    if (match) {
      if (readFail) {
        readFail = false
        return reply(null, 404, 'not accessible')
      }
      return reply(reports[match[1]])
    }
    if (path === '/pareto/analyze') {
      const payload = request.postDataJSON()
      requests.push(payload)
      process.stdout.write(`Analyzing ${requests.length}: ${payload.budgets}\n`)
      if (failNext) {
        failNext = false
        return reply(null, 500, 'analysis failed')
      }
      const r = analyze(payload)
      const delay = delayed
      delayed = null
      if (delay)
        await new Promise((resolve) => {
          release = resolve
        })
      if (delay === 'error') return reply(null, 500, 'stale failure')
      return r.status === 200
        ? reply(r.body.data)
        : reply(null, r.status, r.body.detail)
    }
    unknown.push(path)
    return reply(null, 404)
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.goto(
    `${process.env.EXPERIMENT_BASE_URL || 'http://127.0.0.1:5180'}/experiments/exp-524`,
  )
  await page.getByRole('tab', { name: '帕累托', exact: true }).click()
  const table = page.getByRole('table', { name: '帕累托预算建议', exact: true })
  const budget = page.getByLabel('预算列表（USD，可选）', { exact: true })
  const selection = page.getByLabel('分析实验', { exact: true })
  const retry = () => page.getByRole('button', { name: /重\s*试/, exact: true })
  await table.waitFor()
  assert.deepEqual(requests.at(-1).budgets, [])
  assert.equal(requests.at(-1).comparisons.length, 1)
  await retry().click()
  await page
    .getByRole('button', { name: '加载更多实验', exact: true })
    .waitFor()
  await budget.fill('0, 0.012345 2 2')
  await table.waitFor()
  assert.deepEqual(requests.at(-1).budgets, [0, 0.012345, 2, 2])
  assert.equal(await table.locator('tbody tr').count(), 3)
  for (const value of ['-1', 'NaN', 'Infinity', 'abc', '1e309']) {
    const count = requests.length
    await budget.fill(value)
    await page
      .getByText('预算列表须为有限非负数，以逗号或空白分隔', { exact: true })
      .waitFor()
    assert.equal(await table.count(), 0)
    await setTimeout(50)
    assert.equal(requests.length, count)
  }
  await budget.fill('0 0.012345 2')
  await table.waitFor()
  await selection.click()
  await page
    .locator('.ant-select-dropdown:visible')
    .getByText('exp-second (exp-second)', { exact: true })
    .click()
  await page.keyboard.press('Escape')
  await table.waitFor()
  assert.equal(requests.at(-1).comparisons.length, 2)
  assert.deepEqual(
    requests.at(-1).comparisons.map((r) => r.experiment.experiment_id),
    ['exp-524', 'exp-second'],
  )
  await page.getByLabel('帕累托准确率口径', { exact: true }).click()
  await page
    .locator('.ant-select-dropdown:visible')
    .locator('.ant-select-item-option-content')
    .getByText('formal', { exact: true })
    .click()
  await table.waitFor()
  assert.equal(requests.at(-1).accuracy_metric, 'formal')
  assert.match(await table.innerText(), /不可行/)
  const expected = analyze(requests.at(-1)).body.data
  assert.equal(
    expected.points.find(
      (point) => point.id === expected.budget_recommendations.at(-1).point_id,
    ).model,
    'premium',
  )
  assert.match(
    await page.getByText('前沿组合：', { exact: false }).innerText(),
    /premium/,
  )
  for (const [
    index,
    recommendation,
  ] of expected.budget_recommendations.entries()) {
    const cells = await table
      .locator('tbody tr')
      .nth(index)
      .locator('td')
      .allTextContents()
    assert.deepEqual(cells, [
      String(recommendation.budget_usd),
      recommendation.feasible ? '可行' : '不可行',
      recommendation.point_id || '—',
    ])
  }

  await page.getByRole('button', { name: '加载更多实验', exact: true }).click()
  await selection.click()
  await page
    .locator('.ant-select-dropdown:visible')
    .getByText('exp-bad (exp-bad)', { exact: true })
    .click()
  await page.keyboard.press('Escape')
  await page.getByText(/Experiments have different datasets/).waitFor()
  assert.equal(await table.count(), 0)
  // Remove incompatible selection using its tag close button.
  await page
    .locator('.ant-select-selection-item')
    .filter({ hasText: 'exp-bad' })
    .locator('.ant-select-selection-item-remove')
    .click()
  await table.waitFor()
  const count = requests.length
  readFail = true
  await budget.fill('3')
  await page.getByText('not accessible', { exact: true }).waitFor()
  assert.equal(requests.length, count)
  assert.equal(await table.count(), 0)
  await retry().click()
  await table.waitFor()
  failNext = true
  await budget.fill('4')
  await retry().waitFor()
  assert.equal(await budget.isEditable(), true)
  assert.equal(await table.count(), 0)
  await retry().click()
  await table.waitFor()
  for (const kind of ['success', 'error']) {
    release = undefined
    delayed = kind
    await budget.fill(kind === 'success' ? '5' : '7')
    await eventually(() => assert.equal(typeof release, 'function'))
    assert.equal(await table.count(), 0)
    await budget.fill('6')
    await table.waitFor()
    release()
    await setTimeout(200)
    assert.equal(await budget.inputValue(), '6')
    assert.equal(await table.count(), 1)
    assert.equal(
      await page.getByText('stale failure', { exact: true }).count(),
      0,
    )
  }
  // Empty selection prevents submission, then restoring current experiment recovers.
  while (await page.locator('.ant-select-selection-item-remove').count())
    await page.locator('.ant-select-selection-item-remove').first().click()
  await page.getByText('请选择至少一个实验', { exact: true }).waitFor()
  assert.equal(await table.count(), 0)
  await selection.click()
  await page
    .locator('.ant-select-dropdown:visible')
    .locator('.ant-select-item-option-content')
    .getByText('exp-524', { exact: true })
    .click()
  await page.keyboard.press('Escape')
  await table.waitFor()
  delayed = 'success'
  release = undefined
  await budget.fill('8')
  await eventually(() => assert.equal(typeof release, 'function'))
  await page.goto(
    `${process.env.EXPERIMENT_BASE_URL || 'http://127.0.0.1:5180'}/experiments/exp-other`,
  )
  release()
  await page.getByRole('tab', { name: '帕累托', exact: true }).click()
  await table.waitFor()
  assert.equal(await budget.inputValue(), '')
  assert.equal(
    requests.at(-1).comparisons[0].experiment.experiment_id,
    'exp-other',
  )
  await page.screenshot({ path: resolve(out, 'pareto.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: resolve(out, 'pareto-mobile.png'),
    fullPage: true,
  })
  assert.deepEqual(errors, [])
  assert.deepEqual(unknown, [])
  writeFileSync(
    resolve(out, 'result.json'),
    JSON.stringify({ passed: true, requests }, null, 2),
  )
  process.stdout.write(
    `Passed Pareto browser and real API scenarios. Evidence: ${out}\n`,
  )
} finally {
  release?.()
  await browser.close()
}
