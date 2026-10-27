/* global document, localStorage, innerWidth, getComputedStyle */
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.SHELL_BASE_URL || 'http://127.0.0.1:5180'
const out = resolve(
  process.env.SHELL_QA_DIR || '../docs/superpowers/reports/assets/issue168',
)
await mkdir(out, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
})
const checks = []
const errors = []
let role = 'user'
let authCalls = 0
const requests = []
const unknown = []
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: 'reduce',
})
const page = await context.newPage()
page.on('pageerror', (error) => errors.push(error.message))
await context.route('**/api/v1/**', async (route) => {
  const path = new URL(route.request().url()).pathname
  const pagePath = new URL(route.request().frame().url()).pathname
  requests.push({ path, method: route.request().method(), pagePath })
  const headers = {
    'access-control-allow-origin': base,
    'access-control-allow-credentials': 'true',
  }
  if (route.request().method() === 'OPTIONS')
    return route.fulfill({
      status: 204,
      headers: {
        ...headers,
        'access-control-allow-methods': 'GET,POST,PATCH,DELETE',
        'access-control-allow-headers': 'content-type,x-csrf-token',
      },
    })
  if (path.endsWith('/users/me'))
    return route.fulfill({
      headers,
      json: {
        data: {
          username: 'browser-fixture',
          role,
          email: 'fixture@example.com',
          created_at: '2026-10-20',
        },
      },
    })
  if (path.endsWith('/auth/logout')) {
    authCalls++
    return route.fulfill({ status: 204, headers })
  }
  // 真实创建页的只读接口按仓库既有 fixture 契约应答；其余业务请求仍然报错。
  if (route.request().method() === 'GET' && path.endsWith('/api-keys'))
    return route.fulfill({
      headers,
      json: {
        data: [
          {
            id: 'key-shell',
            key_name: '密钥 S',
            provider: 'openai',
            created_at: 1792533600,
            last_used_at: null,
            verified: true,
            usage_count: 0,
            masked_preview: null,
          },
        ],
      },
    })
  if (
    route.request().method() === 'GET' &&
    path.endsWith('/evaluation-options')
  )
    return route.fulfill({
      headers,
      json: {
        data: {
          strategies: [{ name: 'direct' }, { name: 'reflexion' }],
          sources: [
            { id: 'shared', label: '共享题目', problem_count: 21 },
            { id: 'personal', label: '个人题目', problem_count: 1 },
          ],
        },
      },
    })
  if (
    route.request().method() === 'GET' &&
    path.endsWith('/evaluation-options/models')
  )
    return route.fulfill({
      headers,
      json: {
        data: { provider: 'openai', models: ['model-a'], complete: true },
      },
    })
  if (
    route.request().method() === 'GET' &&
    path.endsWith('/evaluation-options/problems')
  )
    return route.fulfill({
      headers,
      json: {
        data: {
          items: [
            {
              problem_id: 'p1',
              title: '算法题 1',
              difficulty: 'easy',
              source: 'shared',
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      },
    })
  unknown.push({ path, method: route.request().method(), pagePath })
  return route.fulfill({
    status: 500,
    headers,
    json: { message: `Unexpected business API: ${path}` },
  })
})
async function signIn(marker = 'qa-session-a') {
  await page.goto(`${base}/login`)
  await page.evaluate(
    (marker) =>
      localStorage.setItem(
        'llm-harness-session',
        JSON.stringify({
          marker,
          username: 'browser-fixture',
          expiresAt: Date.now() + 3600000,
        }),
      ),
    marker,
  )
  await page.goto(base)
  await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
}
async function chooseAntSelect(label, option) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  // The virtual accessibility list contains only active neighbors; use the visible option.
  await page
    .locator('.ant-select-dropdown:visible .ant-select-item-option')
    .filter({ hasText: new RegExp(`^${option}$`) })
    .click()
}

async function placeholderContrast() {
  return page
    .getByLabel('搜索评估任务', { exact: true })
    .evaluate((element) => {
      const raw = getComputedStyle(element, '::placeholder')
        .color.match(/[0-9.]+/g)
        .map(Number)
      const bg = getComputedStyle(element.closest('.ant-input-affix-wrapper'))
        .backgroundColor.match(/[0-9.]+/g)
        .map(Number)
      const alpha = raw[3] ?? 1
      const fg = raw.slice(0, 3).map((x, i) => x * alpha + bg[i] * (1 - alpha))
      const lum = (values) =>
        values
          .slice(0, 3)
          .map((x) => x / 255)
          .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
          .reduce((sum, x, i) => sum + x * [0.2126, 0.7152, 0.0722][i], 0)
      return (
        (Math.max(lum(bg), lum(fg)) + 0.05) /
        (Math.min(lum(bg), lum(fg)) + 0.05)
      )
    })
}

try {
  await page.goto(`${base}/benchmarks`)
  await page.waitForURL('**/login')
  checks.push('anonymous route redirects to login')
  const loginContrast = await page
    .locator('button.ant-btn-primary[type=submit]')
    .evaluate((element) => {
      const css = getComputedStyle(element)
      const luminance = (value) => {
        const channels = value
          .match(/[0-9.]+/g)
          .slice(0, 3)
          .map(Number)
          .map((x) => x / 255)
          .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
        return (
          channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
        )
      }
      const a = luminance(css.color),
        b = luminance(css.backgroundColor)
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    })
  assert.ok(
    loginContrast >= 4.5,
    `Login button contrast ${loginContrast.toFixed(2)}:1`,
  )
  checks.push(`auth button contrast ${loginContrast.toFixed(2)}:1`)

  await signIn()
  assert.equal(
    await page.getByRole('link', { name: '系统状态', exact: true }).count(),
    0,
  )
  // Six themes at every specified breakpoint; screenshots of desktop and phone.
  for (const variant of ['orbit', 'precision', 'studio']) {
    await page.getByLabel('选择页面风格', { exact: true }).selectOption(variant)
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('主题偏好', { exact: true }).selectOption(theme)
      await page.waitForFunction(() => {
        const input = document.querySelector('.ant-input-affix-wrapper')
        let hex = getComputedStyle(document.documentElement)
          .getPropertyValue('--bg')
          .trim()
          .replace('#', '')
        if (hex.length === 3) hex = [...hex].map((c) => c + c).join('')
        const rgb = `rgb(${[0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`
        return input && getComputedStyle(input).backgroundColor === rgb
      })
      assert.ok(
        (await placeholderContrast()) >= 4.5,
        `${variant}/${theme} placeholder contrast`,
      )
      for (const width of [320, 390, 768, 1024, 1280, 1440]) {
        await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 })
        const size = await page.evaluate(() => ({
          width: innerWidth,
          scroll: document.documentElement.scrollWidth,
          design: document.documentElement.dataset.design,
          theme: document.documentElement.dataset.theme,
        }))
        assert.equal(size.scroll, width, JSON.stringify(size))
        assert.equal(size.design, variant)
        assert.equal(size.theme, theme)
        checks.push(size)
      }
    }
  }
  await page.reload()
  await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
  // System theme changes use the same source as the CSS root and AntD provider.
  await page.getByLabel('主题偏好', { exact: true }).selectOption('system')
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.waitForFunction(
    () => document.documentElement.dataset.theme === 'dark',
  )
  await page.emulateMedia({ colorScheme: 'light' })
  await page.waitForFunction(
    () => document.documentElement.dataset.theme === 'light',
  )
  checks.push('system theme follows media changes')
  await page.getByRole('button', { name: '折叠侧边栏', exact: true }).click()
  await page.waitForFunction(
    () =>
      Math.round(
        document.querySelector('.sidebar').getBoundingClientRect().width,
      ) === 76,
  )
  assert.equal(
    Math.round((await page.locator('.sidebar').boundingBox()).width),
    76,
  )
  await page.reload()
  await page.getByRole('button', { name: '展开侧边栏', exact: true }).waitFor()
  assert.equal(
    await page.getByLabel('选择页面风格', { exact: true }).inputValue(),
    'studio',
  )
  await page.getByRole('button', { name: '展开侧边栏', exact: true }).click()
  checks.push('collapse and appearance persist across reload')
  // 示例仪表盘承载 Mock 列表交互；真实评估页业务由 verify-evaluations 覆盖。
  await page.getByLabel('搜索评估任务', { exact: true }).fill('Qwen')
  await chooseAntSelect('任务状态', '已完成')
  await page.waitForFunction(
    () => document.querySelectorAll('.run-row').length === 1,
  )
  assert.equal(await page.locator('.run-row').count(), 1)
  await page
    .getByRole('button', { name: '通知中心，2 条未读', exact: true })
    .click()
  await page.getByRole('button', { name: '全部已读', exact: true }).click()
  await page.keyboard.press('Escape')
  await page.locator('.notification-drawer').waitFor({ state: 'hidden' })
  await page
    .getByRole('button', { name: '通知中心，0 条未读', exact: true })
    .waitFor()
  assert.equal(
    await page
      .getByRole('button', { name: '通知中心，0 条未读', exact: true })
      .evaluate((e) => document.activeElement === e),
    true,
  )
  // The input DOM node remains mounted on a cosmetic switch.
  await page.getByLabel('搜索评估任务', { exact: true }).evaluate((e) => {
    e.dataset.qaIdentity = 'retained'
  })
  for (const variant of ['orbit', 'precision', 'studio']) {
    await page.getByLabel('选择页面风格', { exact: true }).selectOption(variant)
    assert.equal(new URL(page.url()).pathname, '/')
    assert.equal(
      await page.getByLabel('搜索评估任务', { exact: true }).inputValue(),
      'Qwen',
    )
    assert.equal(
      await page
        .getByLabel('搜索评估任务', { exact: true })
        .getAttribute('data-qa-identity'),
      'retained',
    )
    await page.waitForFunction(
      () => document.querySelectorAll('.run-row').length === 1,
    )
    assert.equal(await page.locator('.run-row').count(), 1)
    assert.equal(
      await page
        .getByRole('button', { name: '通知中心，0 条未读', exact: true })
        .count(),
      1,
    )
  }
  checks.push(
    'variant changes retain route, DOM, filter and notification read state',
  )
  // 统一创建入口：侧栏按钮与快速操作都落到真实创建页，不再弹出模拟表单。
  await page
    .locator('.side-bottom')
    .getByRole('button', { name: '创建评估', exact: true })
    .click()
  await page.waitForURL('**/evaluations/new')
  await page.getByRole('heading', { name: '创建评估', exact: true }).waitFor()
  assert.equal(await page.getByText('确认示例配置', { exact: true }).count(), 0)
  assert.equal(
    await page.locator('.breadcrumbs [aria-current="page"]').innerText(),
    '创建评估',
  )
  checks.push('sidebar create entry navigates to the real create page')
  await page.goto(`${base}/`)
  await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
  await page.getByRole('button', { name: '快速操作', exact: true }).click()
  await page.getByRole('menuitem', { name: '创建评估', exact: true }).click()
  await page.waitForURL('**/evaluations/new')
  await page.getByRole('heading', { name: '创建评估', exact: true }).waitFor()
  checks.push('quick action create entry navigates to the real create page')
  await page.goto(`${base}/`)
  await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
  await chooseAntSelect('预览数据状态', '状态：错误')
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await page.getByRole('status').filter({ hasText: '正在加载数据' }).waitFor()
  await page
    .getByRole('table', { name: 'Mock 评估任务', exact: true })
    .waitFor()
  await chooseAntSelect('预览数据状态', '状态：空数据')
  await page.getByRole('button', { name: '创建首个评估', exact: true }).click()
  await page.waitForURL('**/evaluations/new')
  await page.getByRole('heading', { name: '创建评估', exact: true }).waitFor()
  checks.push('empty state create entry navigates to the real create page')
  await page.goto(`${base}/`)
  await page.getByRole('heading', { name: '仪表盘', exact: true }).waitFor()
  checks.push('loading, empty, error and retry work')
  // goto 触发整页重载，通知 store 回到种子状态（2 条未读）。
  await page
    .getByRole('button', { name: '通知中心，2 条未读', exact: true })
    .click()
  await chooseAntSelect('通知分类', '预算预警')
  assert.equal(await page.locator('.notification-item').count(), 1)
  await page.getByRole('button', { name: '清空通知', exact: true }).click()
  await page.getByText('这里的通知已处理完毕', { exact: true }).waitFor()
  await page.keyboard.press('Escape')
  await page.goto(`${base}/settings/system`)
  await page.getByText('无权访问此页面', { exact: true }).waitFor()
  checks.push('ordinary user cannot open admin route')
  await page.goto(base)
  await page.setViewportSize({ width: 320, height: 844 })
  await page.getByRole('button', { name: '打开导航菜单', exact: true }).click()
  await page.getByRole('link', { name: '帮助文档', exact: true }).last().click()
  await page.getByRole('heading', { name: '帮助文档', exact: true }).waitFor()
  await page
    .getByRole('navigation', { name: '常用页面', exact: true })
    .getByRole('link', { name: '仪表盘', exact: true })
    .click()
  await page.getByRole('button', { name: '打开导航菜单', exact: true }).click()
  await page.keyboard.press('Escape')
  await page.locator('.navigation-drawer').waitFor({ state: 'hidden' })
  assert.equal(
    await page
      .getByRole('button', { name: '打开导航菜单', exact: true })
      .evaluate((e) => document.activeElement === e),
    true,
  )
  checks.push('mobile drawer, bottom navigation and Escape focus restoration')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: '帮助文档', exact: true }).click()
  for (const name of ['成功提示', '错误提示', '警告提示', '信息提示']) {
    await page.getByRole('button', { name, exact: true }).click()
    await page.getByRole('button', { name: `关闭${name}`, exact: true }).click()
  }
  await page
    .getByRole('button', { name: '用户菜单：browser-fixture', exact: true })
    .click()
  await page.getByRole('menuitem', { name: '登出', exact: true }).click()
  await page.waitForURL('**/login')
  assert.equal(authCalls, 1)
  assert.equal(
    await page.evaluate(() => localStorage.getItem('llm-harness-session')),
    null,
  )
  await signIn('qa-session-b')
  await page
    .getByRole('button', { name: '通知中心，2 条未读', exact: true })
    .waitFor()
  checks.push(
    'four dismissible toasts, real logout client and session notification isolation',
  )
  role = 'admin'
  await page.reload()
  await page.getByRole('link', { name: '系统状态', exact: true }).waitFor()
  checks.push('admin navigation uses server role')
  const boundaryPage = await context.newPage()
  const intentionalErrors = []
  boundaryPage.on('pageerror', (error) => intentionalErrors.push(error.message))
  await boundaryPage.goto(`${base}/scripts/fixtures/error-boundary.html`)
  await boundaryPage.getByText('页面暂时无法显示', { exact: true }).waitFor()
  await boundaryPage
    .getByRole('button', { name: '修复模拟异常', exact: true })
    .click()
  await boundaryPage
    .getByRole('button', { name: '重试页面', exact: true })
    .click()
  await boundaryPage.getByText('页面已恢复', { exact: true }).waitFor()
  assert.ok(
    intentionalErrors.every((message) =>
      message.includes('intentional-boundary-fixture'),
    ),
  )
  await boundaryPage.close()
  checks.push('real render exception is caught and recovers after retry')
  role = 'user'
  for (const variant of ['orbit', 'precision', 'studio']) {
    await page.getByLabel('选择页面风格', { exact: true }).selectOption(variant)
    for (const width of [390, 1440]) {
      await page
        .getByLabel('主题偏好', { exact: true })
        .selectOption(width === 1440 && variant === 'orbit' ? 'dark' : 'light')
      const capture = await context.newPage()
      capture.on('pageerror', (error) => errors.push(error.message))
      await capture.setViewportSize({
        width,
        height: width === 390 ? 844 : 1000,
      })
      await capture.goto(base)
      await capture
        .getByRole('heading', { name: '仪表盘', exact: true })
        .waitFor()
      await capture.evaluate(() => document.fonts.ready)
      await capture.screenshot({ path: `${out}/${variant}-${width}.png` })
      if (width === 390) {
        await capture.locator('.recent').scrollIntoViewIfNeeded()
        await capture.screenshot({
          path: `${out}/${variant}-${width}-list.png`,
        })
      }
      await capture.close()
    }
  }
  assert.deepEqual(errors, [])
  // 真实创建页的只读接口属于预期内业务请求；外壳自身不得发起其余业务请求。
  const shellEndpoints = ['/users/me', '/auth/logout']
  const createPageReads = [
    '/api-keys',
    '/evaluation-options',
    '/evaluation-options/models',
    '/evaluation-options/problems',
  ]
  const mockRequests = requests.filter((request) =>
    ['/', '/help'].includes(request.pagePath),
  )
  assert.equal(
    mockRequests.some(
      (request) => !shellEndpoints.some((path) => request.path.endsWith(path)),
    ),
    false,
  )
  assert.deepEqual(unknown, [])
  checks.push(
    'Mock dashboard/help issue no business requests; real create page has declared read requests',
  )
  assert.equal(
    requests.some(
      (r) =>
        !shellEndpoints.some((p) => r.path.endsWith(p)) &&
        !(
          r.method === 'GET' && createPageReads.some((p) => r.path.endsWith(p))
        ),
    ),
    false,
  )
  await writeFile(
    `${out}/checks.json`,
    JSON.stringify(
      {
        layer: 'browser-fixture (not backend E2E)',
        replaced: [
          'identity/logout HTTP',
          'creation option HTTP',
          'dashboard/help business data',
        ],
        real: ['React shell', 'router', 'shared auth client', 'creation page'],
        mockPagePaths: ['/', '/help'],
        checks,
        requests,
        unknown,
        pageErrors: errors,
      },
      null,
      2,
    ),
  )
  console.log(
    `PASS: ${checks.length} browser checks; Mock regions make no business requests, real create reads are declared, no unknown requests or page errors. Evidence: ${out}`,
  )
} catch (error) {
  await page.screenshot({ path: `${out}/failure.png` })
  console.log((await page.locator('body').innerText()).slice(-4000))
  console.log(
    await page.locator('.ant-select-dropdown').evaluateAll((elements) =>
      elements.map((e) => ({
        text: e.textContent,
        rect: e.getBoundingClientRect().toJSON(),
      })),
    ),
  )
  throw error
} finally {
  await browser.close()
}
