import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { createRequire } from 'node:module'
import process from 'node:process'

// Run against a disposable API database. The repeated StrictMode loads need
// a higher AUTH_PROTECTED_RATE_LIMIT than the default (e.g. 1000).
const { chromium, request } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || 'playwright',
)
const ui = process.env.BUDGET_HTTP_UI || 'http://127.0.0.1:3000'
const api = await request.newContext({
  baseURL: process.env.BUDGET_HTTP_API || 'http://127.0.0.1:8000',
})
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || undefined,
})
const budgetPath = '/api/v1/budgets'

async function data(response, expectedStatus = 200) {
  assert.equal(response.status(), expectedStatus)
  return (await response.json()).data
}

try {
  const username = 'budget-' + randomUUID().slice(0, 10)
  const password = 'a-long-test-password-!'
  await data(
    await api.post('/api/v1/auth/register', {
      data: { username, email: `${username}@example.org`, password },
    }),
    201,
  )
  const { access_token: token } = await data(
    await api.post('/api/v1/auth/login', { data: { username, password } }),
  )
  const headers = { Authorization: `Bearer ${token}` }
  const page = await browser.newPage()
  page.setDefaultTimeout(12_000)
  await page.goto(`${ui}/login`)
  await page.locator('#login-identity').fill(username)
  await page.locator('#login-password').fill(password)
  await page.locator('button[type="submit"]').click()
  await page.waitForURL((url) => url.pathname !== '/login')

  const globalCap = page.getByLabel('全局预算上限', { exact: true })
  const difficulty = (key) => page.getByLabel(`${key} 难度预算上限`)
  const save = page.getByRole('button', { name: '保存预算', exact: true })
  const budgetSection = page
    .getByRole('heading', { name: '预算配置' })
    .locator('..')
  const route = '**/api/v1/budgets'
  const caps = { easy: 1, medium: 2 }
  const scenarios = [
    { mode: 'normal', difficultyCaps: caps },
    { mode: 'delayed', difficultyCaps: caps },
    { mode: 'failed', difficultyCaps: caps },
    { mode: 'legacy', difficultyCaps: null },
    { mode: 'empty', difficultyCaps: {} },
  ]

  for (const [index, { mode, difficultyCaps }] of scenarios.entries()) {
    const seed = { global_cap_usd: 10, action: 'downgrade' }
    if (difficultyCaps !== null) seed.difficulty_caps = difficultyCaps
    const seeded = await api.post(budgetPath, { headers, data: seed })
    assert.ok(seeded.ok())
    assert.deepEqual((await seeded.json()).data.difficulty_caps, difficultyCaps)

    const { promise: requestStarted, resolve: markStarted } =
      Promise.withResolvers()
    const { promise: releaseRead, resolve: release } = Promise.withResolvers()
    let failRead = mode === 'failed'
    await page.route(route, async (intercept) => {
      if (intercept.request().method() !== 'GET') return intercept.continue()
      markStarted()
      if (mode === 'delayed') await releaseRead
      if (failRead) return intercept.fulfill({ status: 503 })
      await intercept.continue()
    })
    await page.goto(`${ui}/settings/budgets`)
    if (mode === 'delayed') {
      try {
        await Promise.race([
          requestStarted,
          page
            .waitForTimeout(12_000)
            .then(() => assert.fail('Budget GET did not start')),
        ])
        assert.equal(await save.count(), 0, 'Save is available during GET')
      } finally {
        release()
      }
    }
    if (mode === 'failed') {
      const retry = budgetSection.getByRole('button', { name: /重\s*试/ })
      await retry.waitFor()
      assert.equal(await save.count(), 0, 'Save is available after failed GET')
      failRead = false
      await retry.click()
    }

    const updated = 20 + index
    await globalCap.fill(`0${updated}.0`)
    const pending = page.waitForResponse(
      (response) =>
        response.url().endsWith(budgetPath) &&
        response.request().method() === 'PATCH',
    )
    await save.click()
    const response = await pending
    const persisted = await data(await api.get(budgetPath, { headers }))
    assert.deepEqual(
      response.request().postDataJSON(),
      { global_cap_usd: updated },
      mode,
    )
    assert.equal(persisted.global_cap_usd, updated)
    assert.deepEqual(persisted.difficulty_caps, difficultyCaps)
    assert.equal(persisted.action, 'downgrade')
    await page.waitForFunction((value) => {
      const input = globalThis.document.querySelector(
        '[aria-label="全局预算上限"]',
      )
      return input?.value === value
    }, String(updated))

    await page.unrouteAll({ behavior: 'wait' })
    await page.reload()
    await globalCap.waitFor()
    assert.equal(await globalCap.inputValue(), String(updated))
    for (const key of ['easy', 'medium', 'hard']) {
      assert.equal(
        await difficulty(key).inputValue(),
        String(difficultyCaps?.[key] ?? ''),
      )
    }
    process.stdout.write(`PASS ${mode}\n`)
  }

  assert.ok(
    (
      await api.post(budgetPath, { headers, data: { difficulty_caps: caps } })
    ).ok(),
  )
  await page.reload()
  assert.equal(await difficulty('easy').inputValue(), '1')
  await difficulty('easy').fill('')
  const pending = page.waitForResponse(
    (response) =>
      response.url().endsWith(budgetPath) &&
      response.request().method() === 'PATCH',
  )
  await save.click()
  const response = await pending
  assert.deepEqual(response.request().postDataJSON(), {
    difficulty_caps: { medium: 2 },
  })
  const persisted = await data(await api.get(budgetPath, { headers }))
  assert.deepEqual(persisted.difficulty_caps, { medium: 2 })
  process.stdout.write('PASS clear one difficulty cap\n')
} finally {
  await browser.close()
  await api.dispose()
}
