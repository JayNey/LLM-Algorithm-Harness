/* global localStorage, document, window */
// Browser fixtures verify the real forms; backend integration is covered by pytest.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { URL } from 'node:url'
import { tmpdir } from 'node:os'
import process from 'node:process'
import console from 'node:console'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.DATASET_BASE_URL || 'http://127.0.0.1:5180'
const out = process.env.DATASET_QA_DIR || resolve(tmpdir(), 'issue-308-browser')
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
const assertions = []
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
  })
  await context.addInitScript(() => {
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'fixture-user',
        username: 'fixture',
        expiresAt: Date.now() + 3600000,
      }),
    )
  })
  let datasetState = 'ready'
  const submitted = []
  const keys = [
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
  ]
  const suite = {
    id: 'suite',
    name: 'Private suite',
    version: '1.0',
    description: null,
    frozen: false,
    problems: ['p1'],
    created_at: '2026-10-28T00:00:00Z',
    updated_at: '2026-10-28T00:00:00Z',
  }
  const jobs = new Map()
  await context.route('**/api/v1/**', async (route, request) => {
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const method = request.method()
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data, message: '' }),
      })
    if (path === '/datasets') {
      if (datasetState === 'error')
        return route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Unavailable' }),
        })
      return reply(
        datasetState === 'empty'
          ? []
          : [
              {
                id: 'mine',
                name: 'Personal problem collection',
                problem_count: 2,
                updated_at: 0,
              },
            ],
      )
    }
    if (path === '/api-keys') return reply(keys)
    if (path === '/users/me')
      return reply({ id: 'fixture-user', username: 'fixture', role: 'user' })
    if (path === '/evaluation-options')
      return reply({ strategies: [{ name: 'vanilla' }], sources: [] })
    if (path === '/evaluation-options/models')
      return reply({
        provider: 'openai',
        models: ['model-test'],
        complete: true,
        source: 'provider_api',
        scope: 'evaluation',
      })
    if (path === '/benchmarks/suites/suite') return reply(suite)
    if (path === '/benchmarks/learning-curve/suite')
      return reply({
        suite_id: 'suite',
        suite_name: suite.name,
        data: [],
        trends: { accuracy_growth_rate: null, cost_growth_rate: null },
      })
    if (
      method === 'POST' &&
      ['/experiments', '/ab-tests', '/benchmarks/suites/suite/run'].includes(
        path,
      )
    ) {
      const body = request.postDataJSON()
      submitted.push({ path, body })
      const job = {
        id: path === '/ab-tests' ? 'ab-new' : 'exp-new',
        name: body.name ?? '',
        status: 'pending',
        config: { ...body, dataset_path: null },
        task_id: null,
        error_message: null,
        created_at: '2026-10-28T00:00:00Z',
        updated_at: '2026-10-28T00:00:00Z',
      }
      jobs.set(
        path === '/ab-tests' ? '/ab-tests/ab-new' : '/experiments/exp-new',
        job,
      )
      if (path.includes('/benchmarks/'))
        return reply(
          {
            id: 'run',
            suite_id: 'suite',
            status: 'pending',
            model: body.model,
            accuracy: null,
            cost_usd: null,
            error_message: null,
            task_id: 'task',
            created_at: job.created_at,
            updated_at: job.updated_at,
          },
          202,
        )
      return reply(job, 201)
    }
    if (jobs.has(path)) return reply(jobs.get(path))
    if (path === '/tasks/task')
      return reply({
        id: 'task',
        task_type: 'benchmark',
        entity_id: 'run',
        status: 'pending',
        progress: null,
        error_message: null,
        created_at: suite.created_at,
        updated_at: suite.updated_at,
      })
    if (path === '/tasks')
      return reply({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    return route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: '{}',
    })
  })
  const page = await context.newPage()
  const pick = async (label, option) => {
    await page.getByLabel(label, { exact: true }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText(option, { exact: true })
      .click()
  }
  for (const family of ['experiment', 'ab', 'benchmark']) {
    const path = {
      experiment: '/experiments/new',
      ab: '/ab-tests/new',
      benchmark: '/benchmarks/suite',
    }[family]
    await page.goto(`${base}${path}`)
    await pick('选择个人题库', '个人题库 · 2 题')
    assert.equal(
      await page.getByLabel('数据集路径', { exact: true }).count(),
      0,
    )
    if (family === 'experiment') {
      await pick('实验 API Key', 'Test key')
      await page.getByLabel('模型 1 名称', { exact: true }).fill('model-test')
      await page.getByLabel('策略 1 名称', { exact: true }).fill('vanilla')
    } else if (family === 'ab') {
      await pick('A/B 密钥', 'Test key')
      await page.getByLabel('A/B 模型', { exact: true }).fill('model-test')
    } else {
      await pick('基准运行密钥', 'Test key')
      await page.getByLabel('基准运行模型', { exact: true }).fill('model-test')
    }
    await page.getByRole('heading', { level: 1 }).click()
    await page
      .locator('.ant-select-dropdown:visible')
      .first()
      .waitFor({ state: 'hidden' })
    await page.screenshot({
      path: resolve(out, `${family}-desktop.png`),
      fullPage: true,
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({
      path: resolve(out, `${family}-mobile.png`),
      fullPage: true,
    })
    const overflow = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      elements: [...document.querySelectorAll('body *')]
        .filter((element) => {
          const box = element.getBoundingClientRect()
          return box.width > 0 && box.right > window.innerWidth + 1
        })
        .slice(0, 15)
        .map((element) => ({
          tag: element.tagName,
          class: element.className,
          width: element.getBoundingClientRect().width,
          text: element.textContent.slice(0, 90),
        })),
    }))
    if (overflow.width > overflow.viewport)
      console.log(JSON.stringify({ family, overflow }))
    assert.equal(overflow.width <= overflow.viewport, true)
    await page.setViewportSize({ width: 1280, height: 1000 })
    const count = submitted.length
    const response = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes('/api/v1/'),
      { timeout: 5000 },
    )
    await page
      .getByLabel(
        {
          experiment: '提交实验',
          ab: '提交 A/B 测试',
          benchmark: '启动基准运行',
        }[family],
        { exact: true },
      )
      .click()
    await response
    assert.equal(submitted.length, count + 1)
    assert.equal(submitted.at(-1).body.dataset_id, 'mine')
    assert.equal('dataset_path' in submitted.at(-1).body, false)
    assertions.push(
      `${family}: selected personal collection, submitted dataset_id without path, desktop/mobile render`,
    )
  }
  datasetState = 'empty'
  await page.goto(`${base}/experiments/new`)
  await page.getByText('尚无可用个人题目，请先导入题库。').waitFor()
  await page.getByRole('link', { name: '前往题库', exact: true }).waitFor()
  await pick('数据来源', '服务器数据集路径')
  await page
    .getByLabel('数据集路径', { exact: true })
    .fill('datasets/demo.json')
  await pick('数据来源', '个人题库')
  assert.equal(await page.getByLabel('数据集路径', { exact: true }).count(), 0)
  assertions.push(
    'empty collection guidance and mutually exclusive path switching',
  )
  datasetState = 'error'
  await page.goto(`${base}/ab-tests/new`)
  await page.getByText('数据集加载失败', { exact: true }).waitFor()
  datasetState = 'ready'
  await page.getByRole('button', { name: /重\s*试/ }).click()
  await pick('选择个人题库', '个人题库 · 2 题')
  assertions.push('dataset loading failure recovers through retry')
  writeFileSync(
    resolve(out, 'report.json'),
    JSON.stringify(
      {
        layer: 'browser fixtures; backend integration in pytest',
        assertions,
        submitted,
      },
      null,
      2,
    ),
  )
  console.log(
    `PASS: ${assertions.length} browser scenarios, ${submitted.length} source payloads; screenshots in ${out}`,
  )
} finally {
  await browser.close()
}
