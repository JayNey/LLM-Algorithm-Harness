/* global localStorage */
// From frontend: node --experimental-strip-types scripts/verify-optimization-constraints.mjs
// Isolated FastAPI TestClient exercises the real route and shared build_advisory.
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import process from 'node:process'
import { setTimeout } from 'node:timers/promises'
import { URL } from 'node:url'
import { chromium } from 'playwright'
import { createExperimentClient } from '../src/experiments/client.ts'
import { emptyNotificationPage } from './fixtures/notifications.mjs'
const root = resolve(import.meta.dirname, '../..')
const out = process.env.OPTIMIZATION_QA_DIR || '/tmp/issue-523-qa'
mkdirSync(out, { recursive: true })
const combo = (model, solved, cost) => ({
  model,
  strategy: 'direct',
  solved,
  pass_rate_over_total: solved / 6,
  cost: { known: true, total_cost_usd: cost },
  denominator: { total: 6, completed: 6, budget_exhausted: 0 },
  by_difficulty: Object.fromEntries(
    ['easy', 'medium', 'hard'].map((key) => [
      key,
      { solved: solved / 3, total: 2 },
    ]),
  ),
})
const comparison = {
  combinations: [combo('cheap', 3, 1.2), combo('premium', 6, 6)],
}
const python = `
import json, sys
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.ab_tests import router, current_user
from src.cost_optimizer import build_advisory
payload = json.load(sys.stdin)
app = FastAPI()
app.include_router(router)
app.dependency_overrides[current_user] = lambda: object()
with patch('api.routes.ab_tests.build_advisory', wraps=build_advisory) as shared:
    response = TestClient(app).post('/api/v1/optimize', json=payload)
    assert response.status_code == 200, response.text
    shared.assert_called_once_with(payload['comparison'], budget=payload.get('budget'), min_accuracy=payload.get('min_accuracy', 0), objective=payload.get('objective', 'best_value'))
    print(json.dumps(response.json()['data']))
`
function analyze(payload) {
  const result = spawnSync(
    process.env.OPTIMIZATION_PYTHON || resolve(root, '.venv/bin/python'),
    ['-c', python],
    {
      cwd: root,
      input: JSON.stringify(payload),
      encoding: 'utf8',
      timeout: 20000,
    },
  )
  assert.equal(result.status, 0, result.stderr)
  return JSON.parse(result.stdout.trim().split('\n').at(-1))
}
const baseline = analyze({ comparison })
const constrained = analyze({
  comparison,
  budget: 5,
  min_accuracy: 0.8,
  objective: 'lowest_cost',
})
assert.equal(baseline.recommendations.lowest_cost.model, 'cheap')
assert.equal(constrained.recommendations.lowest_cost.model, 'premium')
assert.equal(constrained.budget_plan.estimated_cost, 4)
assert.equal(constrained.budget_plan.coverage, 4)
assert.equal(constrained.budget_plan.layers.hard.feasible, false)
assert.match(constrained.budget_plan.layers.hard.note, /预算不足/)
assert.equal(Object.hasOwn(baseline, 'budget_plan'), false)
let response = constrained
let body
const client = createExperimentClient({
  get: async () => comparison,
  post: async (_url, payload) => {
    body = payload
    return response
  },
})
assert.deepEqual(
  (
    await client.optimize('exp-523', {
      budget: 5,
      minAccuracy: 0.8,
      objective: 'lowest_cost',
    })
  ).budget_plan,
  constrained.budget_plan,
)
assert.equal(body.min_accuracy, 0.8)
assert.equal(body.budget, 5)
response = baseline
await client.optimize('exp-523', {})
assert.equal(Object.hasOwn(body, 'budget'), false)
assert.equal(Object.hasOwn(body, 'min_accuracy'), false)
const impossible = analyze({ comparison, budget: 0.01, min_accuracy: 0.8 })
response = impossible
assert.equal(
  (await client.optimize('exp-523', {})).budget_plan.estimated_accuracy,
  null,
)
for (const bad of [
  null,
  { easy: { feasible: 'yes' } },
  { easy: { feasible: false } },
  { easy: { ...constrained.budget_plan.layers.easy, layer_accuracy: 1.5 } },
]) {
  response = {
    ...constrained,
    budget_plan: { ...constrained.budget_plan, layers: bad },
  }
  await assert.rejects(client.optimize('exp-523', {}), /实验接口响应格式不兼容/)
}
const requests = [],
  unknown = []
let failNext = false,
  delayNext = false,
  release
async function eventually(check) {
  for (let i = 0; i < 100; i++) {
    try {
      await check()
      return
    } catch (error) {
      if (i === 99) throw error
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
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const headers = {
      'access-control-allow-origin': request.headers().origin || '*',
      'access-control-allow-credentials': 'true',
    }
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        headers,
        contentType: 'application/json',
        body: JSON.stringify({
          success: status === 200,
          data,
          message: status === 200 ? '' : 'optimization retry fixture',
        }),
      })
    if (request.method() === 'OPTIONS')
      return route.fulfill({
        status: 204,
        headers: {
          ...headers,
          'access-control-allow-headers': '*',
          'access-control-allow-methods': 'GET,POST,OPTIONS',
        },
      })
    if (path === '/users/me')
      return reply({ id: 'user-523', username: 'fixture', role: 'user' })
    if (path === '/notifications') return reply(emptyNotificationPage)
    if (path === '/experiments/exp-523')
      return reply({
        id: 'exp-523',
        name: 'Optimization fixture',
        status: 'completed',
        config: {
          name: 'Optimization fixture',
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
      })
    if (path === '/experiments/exp-523/comparison') return reply(comparison)
    if (path === '/optimize') {
      const payload = request.postDataJSON()
      requests.push(payload)
      if (failNext) {
        failNext = false
        return reply(null, 500)
      }
      const result = analyze(payload)
      if (delayNext) {
        delayNext = false
        await new Promise((resolve) => {
          release = resolve
        })
      }
      return reply(result).catch((error) => {
        if (
          !/closed|handled|intercept|Invalid InterceptionId/i.test(
            String(error),
          )
        )
          throw error
      })
    }
    unknown.push(path)
    return reply(null, 404)
  })
  const page = await context.newPage()
  page.on('pageerror', (error) => process.stderr.write(`${error.stack}\n`))
  await page.goto(
    `${process.env.EXPERIMENT_BASE_URL || 'http://127.0.0.1:5180'}/experiments/exp-523`,
  )
  await page.getByRole('tab', { name: '成本建议', exact: true }).click()
  const budget = page.getByLabel('优化预算（USD，可选）', { exact: true })
  const accuracy = page.getByLabel('最低准确率（%，可选）', { exact: true })
  const recommendations = page.getByRole('table', {
    name: '优化建议',
    exact: true,
  })
  const lowest = recommendations.locator('tr').filter({ hasText: '最低成本' })
  const plan = page.getByRole('region', { name: '预算方案', exact: true })
  await recommendations.waitFor()
  assert.match(await lowest.innerText(), /cheap/)
  assert.equal(await plan.count(), 0)
  assert.equal(Object.hasOwn(requests.at(-1), 'budget'), false)
  await accuracy.fill('80')
  await eventually(async () =>
    assert.match(await lowest.innerText(), /premium/),
  )
  await budget.fill('5')
  await plan.waitFor()
  assert.equal(requests.at(-1).min_accuracy, 0.8)
  assert.equal(requests.at(-1).budget, 5)
  assert.match(await plan.innerText(), /预算不足/)
  assert.match(await plan.innerText(), /100\.0%/)
  await budget.fill('0.01')
  await eventually(async () => assert.match(await plan.innerText(), /无法估算/))
  for (const value of ['0', '-1', 'Infinity', 'NaN', 'abc', '1e309']) {
    const before = requests.length
    await budget.fill(value)
    await page.getByText('预算须为有限正数', { exact: true }).waitFor()
    await setTimeout(80)
    assert.equal(requests.length, before)
    assert.equal(await recommendations.count(), 0)
  }
  await budget.fill('')
  await recommendations.waitFor()
  for (const value of ['-1', '101', 'Infinity', 'abc']) {
    const before = requests.length
    await accuracy.fill(value)
    await page
      .getByText('最低准确率须为 0–100 的有限数值', { exact: true })
      .waitFor()
    assert.equal(requests.length, before)
  }
  for (const value of ['0', '100', '']) {
    await accuracy.fill(value)
    await recommendations.waitFor()
    if (value) assert.equal(requests.at(-1).min_accuracy, Number(value) / 100)
    else assert.equal(Object.hasOwn(requests.at(-1), 'min_accuracy'), false)
  }
  failNext = true
  await budget.fill('3')
  await page.getByRole('button', { name: /重\s*试/, exact: true }).waitFor()
  assert.equal(await budget.isEditable(), true)
  await page.getByRole('button', { name: /重\s*试/, exact: true }).click()
  await plan.waitFor()
  assert.equal(requests.at(-1).budget, 3)
  delayNext = true
  await budget.fill('2')
  await eventually(() => assert.equal(typeof release, 'function'))
  assert.equal(await recommendations.count(), 0)
  assert.equal(await accuracy.isEditable(), true)
  await budget.fill('5')
  await accuracy.fill('80')
  await eventually(async () =>
    assert.match(await lowest.innerText(), /premium/),
  )
  release()
  await setTimeout(200)
  assert.equal(await budget.inputValue(), '5')
  assert.match(await plan.innerText(), /预算不足/)
  assert.match(await lowest.innerText(), /premium/)
  await page.getByLabel('成本优化目标', { exact: true }).click()
  await page
    .locator('.ant-select-dropdown:visible')
    .getByText('最低成本', { exact: true })
    .click()
  await recommendations.waitFor()
  assert.equal(requests.at(-1).objective, 'lowest_cost')
  await page.screenshot({
    path: resolve(out, 'constraints.png'),
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: resolve(out, 'constraints-mobile.png'),
    fullPage: true,
  })
  assert.deepEqual(unknown, [])
  writeFileSync(
    resolve(out, 'result.json'),
    JSON.stringify(
      { passed: true, requests, api: { baseline, constrained, impossible } },
      null,
      2,
    ),
  )
  process.stdout.write(
    `Passed: client parsing, shared API processing and browser scenarios (${requests.length} optimize requests). Evidence: ${out}\n`,
  )
} finally {
  release?.()
  await browser.close()
}
