/* global localStorage */
import assert from 'node:assert/strict'
import process from 'node:process'
import { Buffer } from 'node:buffer'
import { URL } from 'node:url'
import { chromium } from 'playwright'

const base = process.env.PROBLEM_BASE_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
let activePage
try {
  const context = await browser.newContext({ acceptDownloads: true })
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
  const versions = ['a', 'b'].map((id) => ({
    id,
    name: `Version ${id.toUpperCase()}`,
    problem_count: 1,
  }))
  const snapshots = Object.fromEntries(
    versions.map(({ id }) => [
      id,
      [
        {
          problem_id: `problem-${id}`,
          title: `Problem ${id}`,
          difficulty: 'hard',
          tags: ['array'],
          description: `Complete description ${id}`,
          hidden_test_cases: [{ input: { x: 7 }, expected_output: 8 }],
          judge_config: { comparison: 'exact' },
          source_metadata: { version: id },
        },
      ],
    ]),
  )
  const requests = []
  let mode = 'ready'
  let releaseDownload
  let releaseDetail
  let enteredDownload
  let enteredDetail
  const page = await context.newPage()
  activePage = page
  const errors = []
  const downloads = []
  page.on('pageerror', (error) => {
    errors.push(error.message)
    process.stderr.write(`Page error: ${error.message}\n`)
  })
  page.on('console', (message) => {
    if (message.type() === 'error')
      process.stderr.write(`Browser console: ${message.text()}\n`)
  })
  page.on('requestfailed', (request) =>
    process.stderr.write(
      `Failed request: ${request.url()} ${request.failure()?.errorText}\n`,
    ),
  )
  page.on('download', (download) => downloads.push(download))
  await context.route('**/api/v1/**', async (route, request) => {
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const reply = (data) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data, message: '' }),
      })
    if (path === '/users/me')
      return reply({
        id: 'fixture-user',
        username: 'fixture',
        email: 'fixture@example.org',
        is_active: true,
        is_admin: false,
      })
    if (path === '/notifications')
      return reply({
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
        has_more: false,
        unread_count: 0,
      })
    if (path === '/evaluation-options')
      return reply({
        strategies: [],
        sources: [{ id: 'personal', label: '个人题目', problem_count: 2 }],
      })
    if (path === '/evaluation-options/problems' || path === '/results')
      return reply({
        items: [],
        total: 0,
        limit: 50,
        offset: 0,
        has_more: false,
      })
    if (path === '/problems/governance/versions') return reply(versions)
    const match = path.match(
      /^\/problems\/governance\/versions\/([ab])(?:\/(export|report))?$/,
    )
    if (match) {
      const [, id, kind] = match
      if (!kind) {
        if (mode === 'slow-detail') {
          enteredDetail?.()
          await new Promise((resolve) => {
            releaseDetail = resolve
          })
        }
        return reply({
          ...versions.find((version) => version.id === id),
          problems: snapshots[id],
        })
      }
      requests.push({ id, kind })
      if (mode === 'slow-download') {
        enteredDownload?.()
        await new Promise((resolve) => {
          releaseDownload = resolve
        })
      }
      const status =
        mode === 'legacy'
          ? 409
          : mode === 'missing'
            ? 404
            : mode === 'failed'
              ? 503
              : 200
      return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(
          status !== 200
            ? { detail: 'Unavailable' }
            : kind === 'export'
              ? snapshots[id]
              : {
                  version: versions.find((version) => version.id === id),
                  changes: [
                    {
                      problem_id: `problem-${id}`,
                      original_difficulty: 'easy',
                      new_difficulty: 'hard',
                    },
                  ],
                },
        ),
      })
    }
    return reply([])
  })
  await page.goto(base + '/problems')
  await page.getByRole('button', { name: '批量治理', exact: true }).click()
  await page.getByRole('tab', { name: '题集版本', exact: true }).click()
  const datasetButton = () =>
    page.getByRole('button', { name: '导出版本完整 JSON', exact: true })
  const reportButton = () =>
    page.getByRole('button', { name: '导出标签与难度变更报告', exact: true })
  const choose = async (id) => {
    await page.locator('#dataset-versions').click()
    await page
      .locator('.ant-select-item-option-content')
      .filter({ hasText: `Version ${id.toUpperCase()} ·` })
      .click()
  }
  const content = async (download) => {
    const stream = await download.createReadStream()
    const chunks = []
    for await (const chunk of stream) chunks.push(chunk)
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  }
  const downloadFrom = async (button) => {
    const pending = page.waitForEvent('download')
    await button.click()
    return pending
  }
  assert.equal(await datasetButton().count(), 0)
  await choose('a')
  await datasetButton().waitFor()
  const dataset = await downloadFrom(datasetButton())
  assert.equal(dataset.suggestedFilename(), 'dataset-a.json')
  assert.deepEqual(await content(dataset), snapshots.a)
  const report = await downloadFrom(reportButton())
  assert.equal(report.suggestedFilename(), 'dataset-a-changes.json')
  assert.equal((await content(report)).changes[0].problem_id, 'problem-a')
  assert.deepEqual(requests, [
    { id: 'a', kind: 'export' },
    { id: 'a', kind: 'report' },
  ])
  assert.match(
    await page
      .getByRole('link', { name: '使用此版本创建评估' })
      .getAttribute('href'),
    /dataset_version=a$/,
  )

  mode = 'slow-detail'
  const detailStarted = new Promise((resolve) => {
    enteredDetail = resolve
  })
  await choose('b')
  await detailStarted
  assert.equal(
    await datasetButton().count(),
    0,
    'No download from the previous version during loading',
  )
  mode = 'ready'
  releaseDetail()
  await datasetButton().waitFor()
  const selected = await downloadFrom(datasetButton())
  assert.equal(selected.suggestedFilename(), 'dataset-b.json')
  assert.deepEqual(await content(selected), snapshots.b)

  for (const [nextMode, message] of [
    ['legacy', '此版本没有可追溯的历史变更报告'],
    ['missing', '题集版本不存在或已清理'],
    ['failed', '服务暂时不可用'],
  ]) {
    mode = nextMode
    await reportButton().click()
    await page.getByText(message, { exact: true }).waitFor()
    assert.equal(
      downloads.length,
      3,
      'An error response must not become a downloaded file',
    )
  }
  mode = 'ready'
  assert.equal(
    (await content(await downloadFrom(reportButton()))).version.id,
    'b',
  )

  mode = 'slow-download'
  const downloadStarted = new Promise((resolve) => {
    enteredDownload = resolve
  })
  await datasetButton().evaluate((button) => {
    button.click()
    button.click()
  })
  await downloadStarted
  assert.equal(await reportButton().isDisabled(), true)
  const beforeSwitch = downloads.length
  const requestCount = requests.length
  mode = 'ready'
  await choose('a')
  await datasetButton().waitFor()
  releaseDownload()
  // A new successful download supplies a response barrier for the canceled request.
  assert.deepEqual(
    await content(await downloadFrom(datasetButton())),
    snapshots.a,
  )
  assert.equal(downloads.length, beforeSwitch + 1)
  assert.equal(
    requests.length,
    requestCount + 1,
    'Duplicate clicks submit just one old request',
  )

  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: '/private/tmp/issue-529-version-downloads.png',
    fullPage: true,
  })
  mode = 'slow-download'
  const accountDownload = new Promise((resolve) => {
    enteredDownload = resolve
  })
  await reportButton().click()
  await accountDownload
  const beforeAccount = downloads.length
  await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/store/auth.ts')
    useAuthStore.setState({
      session: {
        marker: 'new-user',
        username: 'new-user',
        expiresAt: Date.now() + 3600000,
      },
    })
  })
  mode = 'ready'
  releaseDownload()
  await page.getByRole('button', { name: '批量治理', exact: true }).waitFor()
  await page.waitForTimeout(200)
  assert.equal(
    downloads.length,
    beforeAccount,
    'Old account response must not download',
  )
  assert.deepEqual(errors, [])
  process.stdout.write(
    'Passed: complete dataset and report bytes, selected version parameters, loading guard, errors/retry, duplicate prevention, version/account races, and evaluation link.\n',
  )
} catch (error) {
  if (activePage) {
    process.stderr.write(
      `Browser failure at ${activePage.url()}\n${await activePage.locator('body').innerText()}\n`,
    )
    await activePage.screenshot({
      path: '/private/tmp/issue-529-browser-failure.png',
      fullPage: true,
    })
  }
  throw error
} finally {
  await browser.close()
}
