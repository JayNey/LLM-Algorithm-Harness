/* global localStorage */
// Run against Vite: node scripts/verify-recommendation-controls.mjs
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import process from 'node:process'
import { URL } from 'node:url'
import { chromium } from 'playwright'
import { emptyNotificationPage } from './fixtures/notifications.mjs'

const root = resolve(import.meta.dirname, '../..')
const out = process.env.RECOMMENDATION_QA_DIR || '/tmp/issue-525-qa'
mkdirSync(out, { recursive: true })
// Use the actual API request model, route and shared analysis. Only storage
// dependencies are replaced with fixed metadata and a 50% failure history.
const python = `
import json, sys
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.evaluation_results import router, current_user, evaluation_results_service, evaluation_options_service
from src.recommender import RecommendationProblem
p=lambda id: RecommendationProblem(problem_id=id,title=id,difficulty='easy',tags=['array'])
catalog={f'candidate-{i:03}':(p(f'candidate-{i:03}'),'shared') for i in range(110)}
history=[({'problem_id':id,'status':status,'evaluation_completed':True},p(id)) for id,status in [('seen-fail','wrong_answer'),('seen-pass','success')]]
app=FastAPI()
app.include_router(router)
app.dependency_overrides[current_user]=lambda: SimpleNamespace(user_id='fixture-user')
app.dependency_overrides[evaluation_results_service]=lambda: SimpleNamespace(recommendation_history=lambda *args:history)
app.dependency_overrides[evaluation_options_service]=lambda: SimpleNamespace(problem_metadata=lambda *args:catalog)
r=TestClient(app).post('/api/v1/results/recommendations/preview',json=json.load(sys.stdin))
assert r.status_code==200,r.text
print(json.dumps(r.json()['data']))
`
function analyze(payload) {
  const result = spawnSync(resolve(root, '.venv/bin/python'), ['-c', python], {
    cwd: root,
    input: JSON.stringify(payload),
    encoding: 'utf8',
    timeout: 20000,
  })
  assert.equal(result.status, 0, result.stderr)
  return JSON.parse(result.stdout.trim().split('\n').at(-1))
}
const pageOf = (items) => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
  has_more: false,
})
const task = {
  evaluation_id: 'mine',
  created_at: '2026-11-27T00:00:00Z',
  updated_at: '2026-11-27T00:00:00Z',
  status: 'completed',
  can_start: false,
  can_cancel: false,
  execution_progress: { completed_units: 2, total_units: 2, percentage: 100 },
  strategy_names: ['vanilla'],
  model: 'fixture',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
}
const requests = [],
  saves = [],
  selectedReads = [],
  unknown = [],
  errors = []
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
let page
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
  })
  await context.addInitScript(() => {
    localStorage.setItem('llm-harness-language', 'zh-CN')
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'fixture-user',
        username: 'fixture',
        expiresAt: Date.now() + 3600000,
      }),
    )
  })
  await context.route('**/api/v1/**', async (route, request) => {
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ success: status < 400, data, message: '' }),
      })
    if (path === '/users/me')
      return reply({
        id: 'fixture-user',
        username: 'fixture',
        email: 'fixture@example.org',
        is_active: true,
        is_admin: false,
      })
    if (path === '/notifications') return reply(emptyNotificationPage)
    if (path === '/evaluations/mine') return reply(task)
    if (path === '/results/mine')
      return reply({
        run_id: null,
        status: 'completed',
        created_at: task.created_at,
        completed_at: task.updated_at,
        strategies: [],
        problems: pageOf([]),
      })
    if (path === '/results') return reply(pageOf([]))
    if (path === '/results/recommendations/preview') {
      const payload = request.postDataJSON()
      requests.push(payload)
      return reply(analyze(payload))
    }
    if (path === '/recommendation-sets') {
      if (request.method() === 'POST') {
        saves.push(request.postDataJSON())
        return reply({ id: 'saved', name: saves.at(-1).name }, 201)
      }
      return reply(
        saves.length ? [{ id: 'saved', name: saves.at(-1).name }] : [],
      )
    }
    if (path === '/recommendation-sets/saved')
      return reply({
        id: 'saved',
        name: saves.at(-1).name,
        unavailable_count: 0,
        problems: saves.at(-1).problem_ids.map((id) => ({
          problem_id: id,
          title: id,
          difficulty: 'easy',
          source: 'shared',
        })),
      })
    if (path === '/evaluation-options/problems/selection') {
      const ids = request.postDataJSON().problem_ids
      selectedReads.push(ids)
      return reply(
        ids.map((id) => ({
          problem_id: id,
          title: id,
          difficulty: 'easy',
          source: 'shared',
        })),
      )
    }
    if (path === '/evaluation-options')
      return reply({
        strategies: [{ name: 'vanilla' }],
        sources: [{ id: 'shared', label: '共享题库', problem_count: 110 }],
      })
    if (path === '/evaluation-options/problems') return reply(pageOf([]))
    if (path === '/api-keys') return reply([])
    unknown.push(path)
    return reply(null, 503)
  })
  page = await context.newPage()
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(
    (process.env.RECOMMENDATION_BASE_URL || 'http://127.0.0.1:5185') +
      '/results/mine',
  )
  await page
    .getByRole('button', { name: '推荐下一轮题目', exact: true })
    .click()
  const dialog = page.getByRole('dialog')
  const threshold = dialog.getByRole('spinbutton', {
    name: '失败率阈值',
    exact: true,
  })
  const limit = dialog.getByRole('spinbutton', {
    name: '推荐数量',
    exact: true,
  })
  const preview = dialog.getByRole('button', { name: '预览推荐', exact: true })
  const choices = dialog.getByRole('checkbox')
  await choices.nth(19).waitFor()
  assert.equal(await choices.count(), 20)
  assert.equal(Number(await threshold.inputValue()), 0.5)
  assert.equal(await limit.inputValue(), '20')
  assert.deepEqual(requests.at(-1), {
    run_ids: ['mine'],
    source: 'all',
    min_samples: 1,
    failure_threshold: 0.5,
    limit: 20,
  })
  await dialog
    .getByText('最多选择、保存和带入评估 100 道题。', { exact: true })
    .waitFor()
  await choices.first().check()
  await threshold.fill('0.75')
  assert.equal(await choices.count(), 0)
  await preview.click()
  await dialog
    .getByText('所选历史中没有达到失败率阈值的题型。', { exact: true })
    .waitFor()
  await threshold.fill('0.5')
  for (const value of ['', '0', '-0.1', '1.1']) {
    await threshold.fill(value)
    assert.equal(await preview.isEnabled(), false, value)
  }
  await threshold.fill('0.5')
  for (const value of ['', '0', '101', '20.5']) {
    await limit.fill(value)
    assert.equal(await preview.isEnabled(), false, value)
  }
  assert.equal(requests.length, 2, 'Invalid edits do not request previews')
  await limit.fill('30')
  await preview.click()
  await choices.nth(29).waitFor()
  assert.equal(await choices.count(), 30)
  assert.equal(requests.at(-1).limit, 30)
  await limit.fill('100')
  await preview.click()
  await choices.nth(99).waitFor()
  assert.equal(await choices.count(), 100)
  await dialog
    .getByRole('spinbutton', { name: '最少样本数', exact: true })
    .fill('3')
  await preview.click()
  await dialog
    .getByText('所选历史中的有效样本不足。请选择更多评估或降低最少样本数。', {
      exact: true,
    })
    .waitFor()
  await dialog
    .getByRole('spinbutton', { name: '最少样本数', exact: true })
    .fill('1')
  await dialog.getByRole('combobox', { name: '候选题库', exact: true }).click()
  await page.getByText('本人导入', { exact: true }).last().click()
  await preview.click()
  await dialog
    .getByText('所选题库中没有匹配的未评估题目。', { exact: true })
    .waitFor()
  await dialog.getByRole('combobox', { name: '候选题库', exact: true }).click()
  await page
    .locator('.ant-select-item-option-content')
    .filter({ hasText: /^全部来源$/ })
    .click()
  await limit.fill('30')
  await preview.click()
  await choices.nth(29).waitFor()
  await choices.nth(25).check()
  await dialog
    .getByRole('textbox', { name: '题集名称', exact: true })
    .fill('Next round')
  await dialog
    .getByRole('button', { name: '保存个人题集', exact: true })
    .click()
  await dialog
    .getByText('题集已保存，可在个人推荐题集中打开。', { exact: true })
    .waitFor()
  assert.deepEqual(saves, [
    { name: 'Next round', problem_ids: ['candidate-025'] },
  ])
  await page.screenshot({ path: out + '/desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await threshold.scrollIntoViewIfNeeded()
  const bounds = await threshold.boundingBox()
  assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 390)
  await page.screenshot({ path: out + '/mobile.png', fullPage: true })
  await dialog.getByRole('tab', { name: '个人推荐题集', exact: true }).click()
  await dialog.getByRole('combobox', { name: '打开题集', exact: true }).click()
  await page.getByText('Next round', { exact: true }).last().click()
  await dialog
    .getByRole('button', { name: '用此题集创建评估', exact: true })
    .click()
  await page.waitForURL('**/evaluations/new')
  await page.getByText('candidate-025', { exact: true }).first().waitFor()
  assert.deepEqual(selectedReads.at(-1), ['candidate-025'])
  assert.deepEqual(unknown, [])
  assert.deepEqual(errors, [])
  process.stdout.write(
    'Passed: defaults, threshold effect, 30/100 candidates, invalid inputs, stale selection clearing, empty states, source, save/reopen/continue IDs, mobile.\n',
  )
} catch (error) {
  if (page) {
    await page.screenshot({ path: out + '/failure.png', fullPage: true })
    process.stderr.write(await page.locator('body').innerText())
  }
  throw error
} finally {
  await browser.close()
}
