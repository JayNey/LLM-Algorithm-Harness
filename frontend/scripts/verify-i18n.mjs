/* global localStorage, document, console */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'
import { URL } from 'node:url'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.I18N_BASE_URL || 'http://127.0.0.1:5193'
const output = resolve(process.env.I18N_QA_DIR || '/tmp/bilingual-ui-qa')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
})
const checks = [],
  errors = []
const expectText = async (page, text) =>
  page.getByText(text, { exact: true }).first().waitFor()
const profile = {
  id: 1,
  username: '中文用户名',
  email: 'ada@example.org',
  role: 'admin',
  created_at: 1700000000,
}
async function contextFor({
  auth = false,
  width = 1440,
  variant = 'orbit',
  theme = 'dark',
  blocked = false,
} = {}) {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    reducedMotion: 'reduce',
  })
  await context.addInitScript(
    ({ auth, variant, theme, blocked }) => {
      if (auth)
        localStorage.setItem(
          'llm-harness-session',
          JSON.stringify({
            marker: 'i18n-fixture',
            username: '中文用户名',
            expiresAt: Date.now() + 3600000,
          }),
        )
      if (!localStorage.getItem('llm-harness-ui'))
        localStorage.setItem(
          'llm-harness-ui',
          JSON.stringify({
            appearanceVariant: variant,
            themes: { [variant]: theme },
          }),
        )
      if (blocked)
        Object.defineProperty(globalThis, 'localStorage', {
          get() {
            throw Error('Storage blocked')
          },
        })
    },
    { auth, variant, theme, blocked },
  )
  const calls = []
  await context.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace('/api/v1', '')
    calls.push(path)
    let data
    if (path === '/users/me') data = profile
    else if (path === '/api-keys') data = []
    else if (['/evaluations', '/experiments', '/ab-tests'].includes(path))
      data = {
        items: [],
        total: 0,
        limit: Number(url.searchParams.get('limit') || 20),
        offset: 0,
        has_more: false,
      }
    else if (path === '/costs/summary') data = { total_cost_usd: 0 }
    else
      return route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: {
            code: 'unavailable',
            message: 'Fixture endpoint unavailable',
          },
        }),
      })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data, message: '' }),
    })
  })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', (e) => errors.push(e.message))
  return { context, page, calls }
}
try {
  {
    const { context, page } = await contextFor()
    await page.goto(base + '/login')
    await expectText(page, '用户名或邮箱')
    await page.locator('#login-identity').fill('Ada')
    await page.locator('button[type=submit]').click()
    await expectText(page, '请输入密码')
    const identity = await page.locator('#login-identity').elementHandle()
    await page.getByRole('combobox', { name: '界面语言' }).selectOption('en-US')
    await expectText(page, 'Enter your password')
    assert.equal(await page.locator('#login-identity').inputValue(), 'Ada')
    assert.equal(
      await identity.evaluate((el) => el.isConnected),
      true,
      'Language change must not remount the input',
    )
    assert.equal(new URL(page.url()).pathname, '/login')
    assert.equal(await page.locator('html').getAttribute('lang'), 'en-US')
    await page.reload()
    await expectText(page, 'Username or email')
    assert.equal(
      await page
        .getByRole('combobox', { name: 'Interface language' })
        .inputValue(),
      'en-US',
    )
    await page
      .getByRole('link', { name: 'Register', exact: true })
      .first()
      .click()
    await expectText(page, 'Confirm password')
    await page.locator('#register-username').fill('Ada')
    await page.locator('#register-password').fill('abc')
    await page.locator('button[type=submit]').click()
    await expectText(page, 'At least 12 characters')
    await page
      .getByRole('combobox', { name: 'Interface language' })
      .selectOption('zh-CN')
    await expectText(page, '至少 12 个字符')
    assert.equal(await page.locator('#register-password').inputValue(), 'abc')
    await page.screenshot({
      path: resolve(output, 'auth-zh.png'),
      fullPage: true,
    })
    checks.push(
      'Authentication: live labels and errors, DOM identity, form values, route, refresh persistence and both languages',
    )
    await context.close()
  }
  {
    const { context, page } = await contextFor({ blocked: true })
    await page.goto(base + '/login')
    await expectText(page, '用户名或邮箱')
    await page.getByRole('combobox', { name: '界面语言' }).selectOption('en-US')
    await expectText(page, 'Username or email')
    checks.push(
      'Blocked localStorage: Chinese default and in-memory English switching',
    )
    await context.close()
  }
  for (const variant of ['orbit', 'precision', 'studio'])
    for (const width of [320, 1440]) {
      const { context, page, calls } = await contextFor({
        auth: true,
        width,
        variant,
        theme: width === 320 ? 'light' : 'dark',
      })
      await page.goto(base + '/settings/profile')
      await page.locator('input[name="username"]').waitFor()
      await page.locator('input[name="username"]').fill('未保存的输入')
      const input = await page
          .locator('input[name="username"]')
          .elementHandle(),
        before = calls.length
      await page
        .getByRole('combobox', { name: '界面语言' })
        .selectOption('en-US')
      await expectText(page, 'Change password')
      assert.equal(
        await page.locator('input[name="username"]').inputValue(),
        '未保存的输入',
      )
      assert.equal(await input.evaluate((el) => el.isConnected), true)
      assert.equal(
        calls.length,
        before,
        'Language switching must not refetch user or business data',
      )
      assert.equal(await page.locator('html').getAttribute('lang'), 'en-US')
      assert.equal(
        await page.locator('.breadcrumbs').innerText(),
        'Workspace\n/\nSettings\n/\nProfile',
      )
      assert.equal(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth,
        ),
        true,
        `English overflow: ${variant}/${width}`,
      )
      await page.screenshot({
        path: resolve(output, `${variant}-${width}-en.png`),
        fullPage: true,
      })
      await page.goto(base + '/evaluations')
      await expectText(page, 'No evaluations yet')
      // Cached AntD options must display their new labels on the same mounted page.
      await page
        .getByRole('combobox', { name: 'Interface language' })
        .selectOption('zh-CN')
      await expectText(page, '全部状态')
      await page
        .getByRole('combobox', { name: '界面语言' })
        .selectOption('en-US')
      await expectText(page, 'All statuses')
      await page.reload()
      await expectText(page, 'No evaluations yet')
      assert.equal(await page.locator('html').getAttribute('lang'), 'en-US')
      checks.push(
        `${variant}/${width}: live shell/profile, unsaved CJK input, no remount/refetch, cached option labels, refresh, no overflow`,
      )
      await context.close()
    }
  assert.deepEqual(errors, [])
  await writeFile(
    resolve(output, 'report.json'),
    JSON.stringify(
      { layer: 'Chromium + HTTP fixtures, no live backend', checks, errors },
      null,
      2,
    ),
  )
  console.log(JSON.stringify({ checks, errors, output }, null, 2))
} finally {
  await browser.close()
}
