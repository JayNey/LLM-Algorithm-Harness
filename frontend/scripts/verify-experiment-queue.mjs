/* global localStorage, document, history, PopStateEvent, setTimeout */
// Browser fixture regressions for #296 and #415; use PLAYWRIGHT_MODULE for an external package.
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
  'poll-failed',
  'poll-completed',
  'poll-cancelled',
  'late-task-on-route-change',
  'late-reconcile-on-signout',
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
    const polledTerminal = scenario.startsWith('poll-')
      ? scenario.slice('poll-'.length)
      : scenario === 'late-reconcile-on-signout'
        ? 'failed'
        : null
    let status =
      polledTerminal || scenario === 'late-task-on-route-change'
        ? 'running'
        : scenario === 'terminal'
          ? 'cancelled'
          : 'pending'
    const taskError = '任务执行失败：模型连接中断'
    const oldError = '上一次失败'
    const reconcile = Promise.withResolvers()
    const lateTask = Promise.withResolvers()
    const reconciling = Promise.withResolvers()
    let taskReads = 0
    let detailReads = 0
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
        detailReads++
        if (!polledTerminal) return reply(row)
        if (detailReads === 1)
          return reply({
            ...row,
            error_message: polledTerminal === 'failed' ? null : oldError,
          })
        reconciling.resolve()
        await reconcile.promise
        return reply({
          ...row,
          name: '已同步的队列实验',
          error_message:
            polledTerminal === 'failed' ? '持久化失败原因' : oldError,
        })
      }
      if (path === '/experiments/other-exp')
        return reply({
          ...job,
          id: 'other-exp',
          name: '另一个实验',
          task_id: null,
        })
      if (path === '/auth/logout') return route.fulfill({ status: 204 })
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
        if (request.method() === 'GET') {
          taskReads++
          if (scenario === 'late-task-on-route-change') {
            await lateTask.promise
            status = 'failed'
          }
          if (polledTerminal && taskReads >= 2) status = polledTerminal
        }
        return reply({
          id: 'queued-task',
          task_type: 'experiment',
          entity_id: job.id,
          status,
          progress: null,
          error_message: status === 'failed' ? taskError : null,
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
      if (polledTerminal) await page.clock.install()
      const pendingTask =
        scenario === 'late-task-on-route-change'
          ? page.waitForRequest('**/api/v1/tasks/queued-task')
          : null
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
      } else if (pendingTask) {
        const oldTask = await pendingTask
        const aborted = page.waitForEvent(
          'requestfailed',
          (req) => req === oldTask,
        )
        await page.evaluate(() => {
          history.pushState(null, '', '/experiments/other-exp')
          globalThis.dispatchEvent(new PopStateEvent('popstate'))
        })
        await page.getByRole('heading', { name: /另一个实验/ }).waitFor()
        await aborted
        lateTask.resolve()
        assert.equal(
          await page.getByText(taskError, { exact: true }).count(),
          0,
        )
      } else if (scenario === 'late-reconcile-on-signout') {
        await page.getByRole('alert').filter({ hasText: taskError }).waitFor()
        await Promise.race([
          reconciling.promise,
          page.waitForEvent('request', {
            predicate: (req) =>
              req.url().endsWith('/api/v1/experiments/queued-exp'),
          }),
        ])
        const aborted = page.waitForEvent('requestfailed', (req) =>
          req.url().endsWith('/api/v1/experiments/queued-exp'),
        )
        await page.getByRole('button', { name: '用户菜单：fixture' }).click()
        await page.getByRole('menuitem', { name: '登出', exact: true }).click()
        await page.waitForURL('**/login')
        await aborted
        reconcile.resolve()
        assert.equal(
          await page.getByText(taskError, { exact: true }).count(),
          0,
        )
      } else if (polledTerminal) {
        const statusLabel = {
          failed: '已失败',
          completed: '已完成',
          cancelled: '已取消',
        }
        await page
          .getByRole('heading', {
            name: new RegExp(statusLabel[polledTerminal]),
          })
          .waitFor()
        if (polledTerminal === 'failed') {
          await page.getByRole('alert').filter({ hasText: taskError }).waitFor()
        } else {
          assert.equal(
            await page.getByText(oldError, { exact: true }).count(),
            0,
          )
        }
        reconcile.resolve()
        await page.getByRole('heading', { name: /已同步的队列实验/ }).waitFor()
        await page.clock.fastForward(9_000)
        assert.equal(taskReads, 2, 'terminal task polling must stop')
        assert.equal(
          detailReads,
          2,
          'reconcile once for the observed terminal task',
        )
        await page.reload()
        await page
          .getByRole('heading', {
            name: new RegExp(statusLabel[polledTerminal]),
          })
          .waitFor()
        if (polledTerminal === 'failed') {
          await page
            .getByRole('alert')
            .filter({ hasText: '持久化失败原因' })
            .waitFor()
        } else {
          assert.equal(
            await page.getByText(oldError, { exact: true }).count(),
            0,
          )
        }
        assert.equal(
          taskReads,
          2,
          'persisted terminal experiments need no task polling',
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
      reconcile.resolve()
      lateTask.resolve()
      await context.close()
    }
  }
} finally {
  await browser.close()
}
assert.deepEqual(failures, [])
