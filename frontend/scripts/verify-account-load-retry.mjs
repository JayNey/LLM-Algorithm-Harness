/* global localStorage */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import { test } from 'node:test'
import { URL } from 'node:url'
import { emptyNotificationPage } from './fixtures/notifications.mjs'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.SETTINGS_BASE_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || undefined,
})

const key = {
  id: 'key-425',
  provider: 'openai',
  key_name: 'fixture-key',
  created_at: 0,
  last_used_at: null,
  usage_count: 0,
  verified: false,
}
const profile = {
  id: 'user-425',
  username: 'fixture',
  email: 'fixture@example.com',
  role: 'user',
  created_at: 0,
}
const suite = {
  id: 'suite-425',
  name: 'Fixture suite',
  version: '1.0',
  description: null,
  frozen: false,
  problems: [],
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:00:00Z',
}

async function fixture(t, path, respond) {
  const context = await browser.newContext()
  t.after(() => context.close())
  await context.addInitScript(() => {
    localStorage.setItem(
      'llm-harness-session',
      JSON.stringify({
        marker: 'user-425',
        username: 'fixture',
        expiresAt: Date.now() + 3_600_000,
      }),
    )
  })
  await context.route('**/api/v1/**', async (route, request) => {
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const method = request.method()
    const headers = {
      'access-control-allow-origin': request.headers().origin ?? '*',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': 'GET, POST, PATCH, DELETE, OPTIONS',
    }
    if (method === 'OPTIONS') return route.fulfill({ status: 204, headers })
    const reply = (data, status = 200) =>
      route.fulfill({ status, headers, json: { success: status < 400, data } })
    if (await respond({ path, method, reply, request })) return
    if (path === '/users/me') return reply(profile)
    if (path === '/notifications') return reply(emptyNotificationPage)
    if (path === '/benchmarks/suites/suite-425') return reply(suite)
    if (path === '/benchmarks/suites/suite-425/runs')
      return reply({
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
        has_more: false,
      })
    if (path === '/benchmarks/learning-curve/suite-425')
      return reply({
        suite_id: suite.id,
        suite_name: suite.name,
        data: [],
        trends: {},
      })
    return reply([])
  })
  const page = await context.newPage()
  page.setDefaultTimeout(6000)
  await page.goto(base + path)
  return { page, content: page.locator('.route-content') }
}

const retry = (scope) => scope.getByRole('button', { name: /^重\s*试$/ })
const shown = (scope, text) => scope.getByText(text, { exact: true }).waitFor()

await test('account and benchmark read recovery', async (t) => {
  await t.test(
    'profile retries GET and restores the editable form',
    async (t) => {
      let status = 500
      let data = null
      const { content } = await fixture(
        t,
        '/settings/profile',
        async ({ path, method, reply }) => {
          if (path !== '/users/me' || method !== 'GET') return false
          await reply(data, status)
          return true
        },
      )
      await content.getByRole('alert').first().waitFor()
      status = 200
      await retry(content).click()
      await shown(content, '暂无个人资料')
      data = profile
      await retry(content).click()
      const email = content.locator('input[type=email]')
      await email.waitFor()
      assert.equal(await email.inputValue(), profile.email)
    },
  )

  await t.test(
    'key list retries after 500 and distinguishes a successful empty response',
    async (t) => {
      let status = 500
      const { content } = await fixture(
        t,
        '/settings/api-keys',
        async ({ path, method, reply }) => {
          if (path !== '/api-keys' || method !== 'GET') return false
          await reply([], status)
          return true
        },
      )
      await content.getByRole('alert').first().waitFor()
      assert.equal(await content.getByText('还没有 API 密钥').count(), 0)
      status = 200
      await retry(content).click()
      await shown(content, '还没有 API 密钥')
      await content.getByRole('button', { name: /添\s*加/ }).waitFor()
    },
  )

  for (const method of ['POST', 'PATCH', 'DELETE']) {
    await t.test(
      `${method} succeeds, then list retry performs only a GET`,
      async (t) => {
        let records = method === 'POST' ? [] : [key]
        let failRead = false
        const writes = []
        let reads = 0
        const { page, content } = await fixture(
          t,
          '/settings/api-keys',
          async ({ path, method: requestMethod, reply }) => {
            if (!path.startsWith('/api-keys')) return false
            if (requestMethod === 'GET') {
              reads++
              await reply(records, failRead ? 500 : 200)
            } else {
              writes.push(requestMethod)
              records =
                method === 'DELETE' ? [] : [{ ...key, key_name: 'updated-key' }]
              failRead = true
              await reply({})
            }
            return true
          },
        )
        if (method === 'POST') {
          const form = content.locator('form')
          await form.locator('input[name=key_name]').fill('updated-key')
          await form.locator('input[type=password]').fill('fixture-key-value')
          await form.getByRole('button', { name: /添\s*加/ }).click()
        } else if (method === 'PATCH') {
          const row = content
            .getByRole('listitem')
            .filter({ hasText: key.key_name })
          await row.getByRole('button', { name: /改\s*名/ }).click()
          await row.getByRole('textbox').fill('updated-key')
          await row.getByRole('button', { name: /保\s*存/ }).click()
        } else {
          const row = content
            .getByRole('listitem')
            .filter({ hasText: key.key_name })
          await row.getByRole('button', { name: /删\s*除/ }).click()
          await page
            .getByRole('dialog')
            .getByRole('button', { name: /删\s*除/ })
            .click()
        }
        await shown(content, '密钥列表加载失败')
        const success = {
          POST: '密钥已添加',
          PATCH: '密钥已改名',
          DELETE: '密钥已删除',
        }[method]
        await shown(content, success)
        const before = reads
        failRead = false
        await retry(content).click()
        await shown(
          content,
          method === 'DELETE' ? '还没有 API 密钥' : 'updated-key',
        )
        assert.equal(reads, before + 1)
        assert.deepEqual(writes, [method])
        assert.equal(
          await content.locator('input[type=password]').inputValue(),
          '',
        )
      },
    )
  }

  for (const records of [[], [key]]) {
    await t.test(
      `benchmark retries only keys and handles ${records.length} keys`,
      async (t) => {
        let status = 500
        let suiteReads = 0
        const { content } = await fixture(
          t,
          '/benchmarks/suite-425',
          async ({ path, method, reply }) => {
            if (path === '/benchmarks/suites/suite-425') suiteReads++
            if (path !== '/api-keys' || method !== 'GET') return false
            await reply(records, status)
            return true
          },
        )
        const run = content.getByRole('tabpanel', { name: '运行', exact: true })
        const launch = run.getByRole('button', { name: '启动基准运行' })
        const select = run.getByRole('combobox', { name: '基准运行密钥' })
        await shown(run, '密钥列表加载失败')
        assert.ok(await launch.isDisabled())
        assert.ok(await select.isDisabled())
        assert.equal(await run.getByText('还没有 API 密钥').count(), 0)
        const before = suiteReads
        status = 200
        await retry(
          run.getByRole('alert').filter({ hasText: '密钥列表加载失败' }),
        ).click()
        if (records.length) {
          await select.press('ArrowDown')
          await select.press('Enter')
          await run.getByTitle(key.key_name, { exact: true }).waitFor()
          assert.ok(await launch.isEnabled())
        } else {
          await shown(run, '还没有 API 密钥')
          assert.ok(await launch.isDisabled())
        }
        assert.equal(suiteReads, before)
      },
    )
  }
  for (const change of ['session', 'route']) {
    await t.test(
      `pending list read is discarded on ${change} change`,
      { timeout: 15_000 },
      async (t) => {
        const oldRequest = Promise.withResolvers()
        const releaseOld = Promise.withResolvers()
        const oldResponse = Promise.withResolvers()
        t.after(() => releaseOld.resolve())
        let newScope = false
        const { page, content } = await fixture(
          t,
          '/settings/api-keys',
          async ({ path, method, reply, request }) => {
            if (path !== '/api-keys' || method !== 'GET') return false
            if (newScope) {
              await reply([{ ...key, key_name: 'current-scope-key' }])
            } else {
              oldRequest.resolve(request)
              await releaseOld.promise
              try {
                await reply([{ ...key, key_name: 'stale-key' }])
              } finally {
                oldResponse.resolve()
              }
            }
            return true
          },
        )
        const request = await oldRequest.promise
        await shown(content, '正在加载密钥列表')
        newScope = true
        if (change === 'session') {
          await page.evaluate(async () => {
            const { useAuthStore } = await import('/src/store/auth.ts')
            const session = useAuthStore.getState().session
            localStorage.setItem(
              'llm-harness-session',
              JSON.stringify({ ...session, marker: 'replacement-425' }),
            )
            useAuthStore.getState().hydrate()
          })
        } else {
          await page
            .getByRole('link', { name: '设置', exact: true })
            .first()
            .click()
          await page.waitForURL('**/settings')
          await content
            .getByRole('link', { name: 'API 密钥', exact: true })
            .click()
        }
        await shown(content, 'current-scope-key')
        releaseOld.resolve()
        await oldResponse.promise
        assert.equal(request.failure()?.errorText, 'net::ERR_ABORTED')
        assert.equal(
          await content.getByText('stale-key', { exact: true }).count(),
          0,
        )
      },
    )
  }
}).finally(() => browser.close())
