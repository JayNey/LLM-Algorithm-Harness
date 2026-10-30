/* global document, localStorage */
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { URL } from 'node:url'
import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import process from 'node:process'
import console from 'node:console'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.FIRST_BATCH_UI_URL
const api = process.env.FIRST_BATCH_API_URL
assert.ok(base && api && process.env.FIRST_BATCH_PASSWORD)
for (const origin of [base, api]) {
  assert.equal(new URL(origin).hostname, '127.0.0.1')
}
const browser = await chromium.launch({
  headless: true,
  channel: process.env.FIRST_BATCH_BROWSER_CHANNEL,
})
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
})
const page = await context.newPage()
page.setDefaultTimeout(20000)
const checks = []
let passed = false
const errors = []
const requests = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('request', (request) => {
  const url = new URL(request.url())
  if (url.pathname.startsWith('/api/'))
    requests.push({ method: request.method(), path: url.pathname })
})
function problem(id, padding = '') {
  return {
    problem_id: id,
    title: id,
    description: 'Return x. ' + padding,
    difficulty: 'easy',
    tags: ['array'],
    test_cases: [{ input: { x: 1 }, expected_output: 1 }],
  }
}
async function upload(data, name = 'problems.json') {
  await page.locator('input[type=file]').setInputFiles({
    name,
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(data)),
  })
}
async function openImport() {
  await page.goto(base + '/problems?source=personal&limit=20&offset=0&import=1')
  await page
    .getByRole('heading', { name: '导入题目（个人题库）', exact: true })
    .waitFor()
}
try {
  await page.goto(base + '/login')
  await page.locator('#login-identity').fill('pr313owner')
  await page.locator('#login-password').fill(process.env.FIRST_BATCH_PASSWORD)
  await page.getByRole('button', { name: /登\s*录/, exact: true }).click()
  await page.waitForURL(base + '/')
  checks.push('real cookie login')

  // Both desktop entry points use the real panel.
  const entries = page.getByRole('button', { name: '导入题目', exact: true })
  await entries.first().click()
  await page.waitForURL(/\/problems\?.*import=1/)
  await page.getByRole('heading', { name: '导入题目（个人题库）' }).waitFor()
  await page.goto(base + '/')
  await page.getByRole('button', { name: '快速操作', exact: true }).click()
  await page.getByRole('menuitem', { name: /导入题目/ }).click()
  await page.waitForURL(/\/problems\?.*import=1/)
  checks.push('desktop sidebar and quick action')

  await openImport()
  await page.reload()
  await page.getByRole('heading', { name: '导入题目（个人题库）' }).waitFor()
  await upload([problem('pr313-direct')])
  const before = requests.filter((r) => r.method === 'POST').length
  await page.getByRole('button', { name: '关闭导入面板' }).click()
  assert.equal(requests.filter((r) => r.method === 'POST').length, before)
  assert.equal(new URL(page.url()).searchParams.get('source'), 'personal')
  assert.equal(new URL(page.url()).searchParams.has('import'), false)
  await page
    .getByRole('button', { name: '导入题目', exact: true })
    .last()
    .click()
  const directResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith('/problems/upload') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '开始导入' }).evaluate((button) => {
    button.click()
    button.click()
  })
  const direct = await directResponse
  assert.equal(direct.status(), 200)
  assert.equal((await direct.json()).data.validation.imported, 1)
  await page.getByRole('status', { name: '导入报告' }).waitFor()
  assert.equal(
    requests.filter((r) => r.path.endsWith('/problems/upload')).length,
    1,
  )
  checks.push(
    'direct import, double click, close before submit, URL refresh and filters',
  )

  // >5 MiB goes through actual upload + queue + worker + polling.
  await upload([problem('pr313-async', 'x'.repeat(5 * 1024 * 1024))])
  const queuedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith('/problems/import') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '开始导入' }).click()
  const queued = await queuedResponse
  assert.equal(queued.status(), 202)
  const jobId = (await queued.json()).data.job_id
  const terminalResponse = await page.waitForResponse(
    async (r) =>
      r.url().endsWith('/imports/' + jobId) &&
      r.status() === 200 &&
      (await r.json()).data.status === 'completed',
    { timeout: 60000 },
  )
  const terminal = (await terminalResponse.json()).data
  assert.equal(terminal.result.imported, 1)
  assert.equal(terminal.result.dataset_total, 2)
  assert.equal(
    requests.filter((r) => r.path.endsWith('/problems/import')).length,
    1,
  )
  checks.push(
    'real large-file upload, Redis enqueue, Celery processing and terminal progress',
  )

  // Exercise overwrite confirmation against the real dataset store.
  await upload([problem('pr313-replaced')])
  await page.getByRole('combobox', { name: '导入模式' }).click()
  await page.getByText('整库替换（清空后导入）', { exact: true }).last().click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: '开始导入' }).click()
  assert.equal(
    requests.filter((r) => r.path.endsWith('/problems/upload')).length,
    1,
  )
  page.once('dialog', (dialog) => dialog.accept())
  const overwriteResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith('/problems/upload') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '开始导入' }).click()
  const overwrite = await overwriteResponse
  assert.equal((await overwrite.json()).data.validation.dataset_total, 1)
  checks.push('overwrite cancel and confirm with real storage')

  await page.setViewportSize({ width: 320, height: 760 })
  await page.goto(base + '/')
  await page.locator('.mobile-import-action').click()
  await page.getByRole('heading', { name: '导入题目（个人题库）' }).waitFor()
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= 320),
  )
  checks.push('320px mobile entry and no overflow')
  await page.setViewportSize({ width: 1440, height: 1000 })

  for (const suffix of ['complete', 'partial']) {
    await page.goto(base + '/results/pr313-' + suffix)
    const section = page.getByRole('region', { name: '下载报告' })
    await section.waitFor()
    assert.equal(
      await section
        .getByText('报告仅包含当前已记录的结果，不代表完整评估。', {
          exact: true,
        })
        .count(),
      suffix === 'partial' ? 1 : 0,
    )
    for (const [format, label, extension] of [
      ['markdown', 'Markdown', 'md'],
      ['html', 'HTML', 'html'],
      ['csv', 'CSV', 'csv'],
    ]) {
      if (suffix === 'complete' && format === 'csv') {
        await context.clearCookies({ name: 'harness_access_token' })
      }
      const responsePromise = page.waitForResponse(
        (r) =>
          r.url().endsWith('/reports/' + format + '/pr313-run-' + suffix) &&
          r.status() === 200,
      )
      const downloadPromise = page.waitForEvent('download')
      await section.getByRole('button', { name: '下载报告 · ' + label }).click()
      const [response, download] = await Promise.all([
        responsePromise,
        downloadPromise,
      ])
      assert.equal(response.status(), 200)
      assert.equal(
        download.suggestedFilename(),
        `pr313-run-${suffix}.${extension}`,
      )
      const bytes = await readFile(await download.path())
      assert.ok(bytes.length > 30)
      // Chromium's response-body protocol strips a leading UTF-8 BOM.
      assert.equal(
        bytes.toString('utf8').replace(/^\uFEFF/, ''),
        (await response.body()).toString('utf8').replace(/^\uFEFF/, ''),
      )
      assert.ok(bytes.toString('utf8').includes('vanilla'))
      if (format === 'csv')
        assert.ok(bytes.toString('utf8').includes('pr313-sum'))
      assert.ok(
        response
          .headers()
          ['content-type'].includes(
            format === 'markdown' ? 'text/markdown' : 'text/' + format,
          ),
      )
    }
  }
  assert.ok(requests.some((r) => r.path.endsWith('/auth/refresh')))
  checks.push(
    'six real report downloads, run IDs, filenames, bytes and partial warning',
  )
  // Other-owner runs are rejected by the actual API, even with a valid cookie.
  const denied = await context.request.get(
    api + '/api/v1/reports/csv/pr313-run-other',
  )
  assert.equal(denied.status(), 404)
  checks.push('real owner isolation')

  await page.goto(base + '/settings/budgets')
  await page.getByText(/COST_ALERT_SMTP_/).waitFor()
  assert.equal(await page.getByText(/投递后端尚未实现/).count(), 0)
  await page.evaluate(() =>
    localStorage.setItem('llm-harness-language', 'en-US'),
  )
  await page.reload()
  await page.getByText(/COST_ALERT_SMTP_/).waitFor()
  assert.ok((await page.locator('main').innerText()).includes('Mock'))
  checks.push('Chinese and English budget guidance on real page')
  await page.goto(base + '/help')
  await page.getByText(/real problem import panel/).waitFor()
  const help = await page.locator('main').innerText()
  assert.ok(help.includes('real problem import panel'))
  assert.ok(help.includes('Download Markdown, HTML and CSV'))
  assert.ok(!help.includes('still a demo interaction'))
  assert.ok(!help.includes('Report downloads are not yet available'))
  checks.push('help agrees with real import and report capabilities')
  assert.deepEqual(errors, [])
  passed = true
  console.log('PASS:', checks.join('; '))
} finally {
  await writeFile(
    process.env.FIRST_BATCH_OUT,
    JSON.stringify(
      {
        layer: 'real-local-api-redis-celery-browser',
        passed,
        checks,
        errors,
        requests,
      },
      null,
      2,
    ) + '\n',
  )
  await browser.close()
}
