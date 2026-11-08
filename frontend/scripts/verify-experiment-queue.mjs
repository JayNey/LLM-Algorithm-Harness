/* global localStorage, setTimeout */
// Browser fixture regression for #296 and #414; use PLAYWRIGHT_MODULE for an external package.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import { emptyNotificationPage } from './fixtures/notifications.mjs'
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
  'cancel-list-success',
  'cancel-list-failure',
  'cancel-list-race',
  'cancel-detail-failure',
  'cancel-detail-race',
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
    const listCancellation = scenario.startsWith('cancel-list-')
    const cancellation = scenario === 'queued' || scenario.startsWith('cancel-')
    let status =
      scenario === 'terminal'
        ? 'cancelled'
        : scenario.endsWith('-race')
          ? 'running'
          : scenario.endsWith('-failure')
            ? 'paused'
            : 'pending'
    const cancelPaths = []
    let reads = 0
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
      if (request.method() === 'GET' && path === '/notifications')
        return reply(emptyNotificationPage)
      const row = { ...job, status }
      if (
        scenario === 'unqueued' ||
        (scenario === 'publish-uncertain' && starts === 0)
      )
        row.task_id = null
      if (scenario.startsWith('legacy')) delete row.task_id
      if (path === '/experiments/queued-exp' && request.method() === 'GET') {
        reads++
        return reply(row)
      }
      if (path === '/experiments') {
        reads++
        return reply({
          items: [row],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        })
      }
      if (path === '/experiments/queued-exp/run') {
        starts++
        if (scenario === 'publish-uncertain')
          return route.fulfill({ status: 503, body: '{}' })
        return reply(row)
      }
      if (path.startsWith('/tasks/') && request.method() === 'DELETE') {
        cancelPaths.push(path)
        await new Promise((resolve) => setTimeout(resolve, 200))
        if (scenario.endsWith('-failure'))
          return route.fulfill({ status: 503, body: '{}' })
        if (scenario.endsWith('-race')) {
          status = 'completed'
          return route.fulfill({
            status: 400,
            json: { detail: '实验已完成' },
          })
        }
        status = 'cancelled'
        return reply(null)
      }
      if (path === '/tasks/queued-task') {
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
      await page.goto(
        `${base}/experiments${listCancellation ? '' : '/queued-exp'}`,
      )
      const experiment = listCancellation
        ? page.getByRole('row', { name: /队列回归实验/ })
        : page
      const heading = page.getByRole('heading', { name: /队列回归实验/ })
      if (listCancellation) await experiment.waitFor()
      else await heading.waitFor()
      const start = page.getByRole('button', { name: '启动实验' })
      const remove = experiment.getByRole('button', {
        name: /删\s*除/,
        exact: true,
      })
      if (cancellation) {
        const cancel = experiment.getByRole('button', {
          name: listCancellation ? '取消运行' : '取消实验',
        })
        const dialog = page.getByRole('dialog', { name: '取消运行' })
        await cancel.waitFor()
        assert.equal(await start.count(), 0)
        if (listCancellation) assert.equal(await remove.count(), 0)
        else assert.ok(await remove.isDisabled())
        if (scenario === 'queued') await page.reload()

        await cancel.press('Enter')
        await dialog.waitFor()
        await page.keyboard.press('Escape')
        await dialog.waitFor({ state: 'hidden' })
        assert.deepEqual(cancelPaths, [])

        await cancel.press('Space')
        await dialog
          .getByRole('button', { name: /返\s*回/, exact: true })
          .click()
        await dialog.waitFor({ state: 'hidden' })
        assert.deepEqual(cancelPaths, [])

        const readsBefore = reads
        await cancel.press('Enter')
        await dialog.getByRole('button', { name: '确认取消' }).dblclick()
        await dialog.waitFor({ state: 'hidden' })

        const expected = scenario.endsWith('-failure')
          ? '已暂停'
          : scenario.endsWith('-race')
            ? '已完成'
            : '已取消'
        if (listCancellation)
          await experiment.getByText(expected, { exact: true }).waitFor()
        else await heading.filter({ hasText: expected }).waitFor()

        // The status already matched before a 503. Require a fresh read and
        // verify the server response still allows cancellation.
        if (scenario.endsWith('-failure')) {
          await page
            .getByRole('alert')
            .filter({ hasText: '服务暂时不可用' })
            .waitFor()
          await cancel.waitFor()
          assert.ok(await cancel.isEnabled())
          if (listCancellation) assert.equal(await remove.count(), 0)
          else assert.ok(await remove.isDisabled())
        } else {
          await remove.waitFor()
          assert.ok(await remove.isEnabled())
          assert.equal(await cancel.count(), 0)
        }
        assert.ok(reads > readsBefore, 'cancellation must refresh server state')
        assert.deepEqual(cancelPaths, ['/tasks/queued-task'])
        assert.equal(
          queries,
          0,
          'explicit association must avoid global task scans',
        )
        assert.equal(starts, 0)
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
