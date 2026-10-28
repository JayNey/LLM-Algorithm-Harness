/* global localStorage, document, setTimeout */
// Browser fixture regression for #296; use PLAYWRIGHT_MODULE for an external package.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.EXPERIMENT_BASE_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
const job = {
  id: 'queued-exp',
  name: '队列回归实验',
  status: 'pending',
  task_id: 'queued-task',
  config: {
    name: '队列回归实验',
    dataset_path: 'demo.json',
    models: [{ model: 'demo' }],
    strategies: [{ name: 'vanilla' }],
    repeats: 1,
    budget: null,
    execution: 'serial',
    max_workers: 1,
  },
  error_message: null,
  created_at: '2026-10-28T00:00:00Z',
  updated_at: '2026-10-28T00:00:00Z',
}
const scenarios = [
  'queued',
  'unqueued',
  'legacy-error',
  'legacy-loading',
  'terminal',
  'publish-uncertain',
]
const failures = []
try {
  for (const scenario of scenarios) {
    const context = await browser.newContext()
    await context.addInitScript(() =>
      localStorage.setItem(
        'llm-harness-session',
        JSON.stringify({
          marker: 'queue-owner',
          username: 'fixture',
          expiresAt: Date.now() + 3_600_000,
        }),
      ),
    )
    let status = scenario === 'terminal' ? 'cancelled' : 'pending'
    let cancelled = 0
    let queries = 0
    let starts = 0
    const errors = []
    await context.route('**/api/v1/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname.replace('/api/v1', '')
      const reply = (data) =>
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ success: true, data, message: '' }),
        })
      const row = { ...job, status }
      if (
        scenario === 'unqueued' ||
        (scenario === 'publish-uncertain' && starts === 0)
      )
        row.task_id = null
      if (scenario.startsWith('legacy')) delete row.task_id
      if (path === '/experiments/queued-exp' && request.method() === 'GET')
        return reply(row)
      if (path === '/experiments')
        return reply({
          items: [row],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        })
      if (path === '/experiments/queued-exp/run') {
        starts++
        if (scenario === 'publish-uncertain')
          return route.fulfill({ status: 503, body: '{}' })
        return reply(row)
      }
      if (path === '/tasks/queued-task') {
        if (request.method() === 'DELETE') {
          cancelled++
          status = 'cancelled'
        }
        return reply({
          id: 'queued-task',
          task_type: 'experiment',
          entity_id: job.id,
          status,
          progress: null,
          error_message: null,
          created_at: job.created_at,
          updated_at: job.updated_at,
        })
      }
      if (path === '/tasks') {
        queries++
        if (scenario === 'legacy-loading')
          await new Promise((resolve) => setTimeout(resolve, 1500))
        if (scenario === 'legacy-error')
          return route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: '队列查询失败' }),
          })
        return reply({
          items: [],
          total: 0,
          limit: 100,
          offset: 0,
          has_more: false,
        })
      }
      if (path === '/users/me')
        return reply({ id: 'queue-owner', username: 'fixture', role: 'user' })
      // Result panels aren't exercised here.
      if (path.includes('/comparison'))
        return route.fulfill({ status: 400, body: '{}' })
      errors.push(`${request.method()} ${path}`)
      return route.fulfill({ status: 599, body: '{}' })
    })
    const page = await context.newPage()
    page.setDefaultTimeout(5000)
    page.on('pageerror', (error) => errors.push(String(error)))
    try {
      await page.goto(`${base}/experiments/queued-exp`)
      await page.getByRole('heading', { name: /队列回归实验/ }).waitFor()
      const start = page.getByRole('button', { name: '启动实验' })
      const remove = page.getByRole('button', { name: /删\s*除/, exact: true })
      if (scenario === 'queued') {
        await page.getByRole('button', { name: '取消实验' }).waitFor()
        assert.equal(await start.count(), 0)
        assert.ok(await remove.isDisabled())
        await page.reload()
        await page.getByRole('button', { name: '取消实验' }).waitFor()
        assert.equal(await start.count(), 0)
        await page.getByRole('button', { name: '取消实验' }).click()
        await page.waitForFunction(() =>
          [...document.querySelectorAll('button')].some(
            (b) => b.textContent.replace(/\s/g, '') === '删除' && !b.disabled,
          ),
        )
        assert.equal(cancelled, 1)
        assert.equal(
          queries,
          0,
          'explicit association must avoid global task scans',
        )
        assert.equal(starts, 0)
        status = 'pending'
        await page.goto(`${base}/experiments`)
        await page.getByRole('button', { name: '取消运行' }).waitFor()
        assert.equal(
          await page
            .getByRole('button', { name: /删\s*除/, exact: true })
            .count(),
          0,
        )
      } else if (scenario === 'publish-uncertain') {
        await start.waitFor()
        await start.click()
        await page.getByRole('button', { name: '取消实验' }).waitFor()
        assert.equal(await start.count(), 0)
        assert.ok(await remove.isDisabled())
        assert.equal(starts, 1)
      } else if (scenario === 'unqueued') {
        await start.waitFor()
        assert.ok(await start.isEnabled())
        assert.ok(await remove.isEnabled())
        assert.equal(queries, 0)
      } else if (scenario === 'legacy-error') {
        await page
          .getByRole('alert')
          .filter({ hasText: '服务暂时不可用' })
          .waitFor()
        assert.ok((await start.count()) === 0 || (await start.isDisabled()))
        assert.ok(await remove.isDisabled())
      } else if (scenario === 'legacy-loading') {
        assert.ok((await start.count()) === 0 || (await start.isDisabled()))
        assert.ok(await remove.isDisabled())
        await start.waitFor()
        assert.ok(await start.isEnabled())
      } else {
        assert.ok(await remove.isEnabled())
        assert.equal(
          await page.getByRole('button', { name: '取消实验' }).count(),
          0,
        )
      }
      assert.deepEqual(errors, [])
      console.log(`PASS ${scenario}`)
    } catch (error) {
      failures.push(`${scenario}: ${error}`)
      console.error(`FAIL ${scenario}: ${error}`)
    } finally {
      await context.close()
    }
  }
} finally {
  await browser.close()
}
assert.deepEqual(failures, [])
