/* global localStorage, document, window */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import process from 'node:process'
import console from 'node:console'
import { URL } from 'node:url'
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || 'playwright',
)
const ui = process.env.BENCHMARK_HTTP_UI,
  suite = process.env.BENCHMARK_HTTP_SUITE
const records = JSON.parse(process.env.BENCHMARK_HTTP_RECORDS)
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
  })
  await context.addCookies(JSON.parse(process.env.BENCHMARK_HTTP_COOKIES))
  await context.addInitScript(
    (session) =>
      localStorage.setItem('llm-harness-session', JSON.stringify(session)),
    JSON.parse(process.env.BENCHMARK_HTTP_SESSION),
  )
  const page = await context.newPage(),
    errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.goto(`${ui}/benchmarks/${suite}?run_id=${records[0].id}&view=kept`)
  await page.getByRole('heading', { name: '运行历史', exact: true }).waitFor()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText(records[0].id, { exact: true })
    .waitFor()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  assert.equal(new URL(page.url()).searchParams.get('run_id'), records[0].id)
  assert.equal(new URL(page.url()).searchParams.get('view'), 'kept')
  await page.reload()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText(records[0].id, { exact: true })
    .waitFor()
  await page.goto(`${ui}/benchmarks/${suite}?run_id=${records[26].id}`)
  await page
    .getByText('任务已暂停，可手动刷新运行状态', { exact: true })
    .waitFor()
  await page.getByTestId('selected-benchmark-run').getByText(/50%/).waitFor()
  await page.goto(`${ui}/benchmarks/${suite}`)
  await page
    .getByRole('link', { name: records[25].id, exact: true })
    .first()
    .waitFor()
  await page
    .getByRole('link', { name: records[26].id, exact: true })
    .first()
    .waitFor()
  assert.equal(new URL(page.url()).searchParams.get('run_id'), null)
  await page.getByRole('tab', { name: '学习曲线', exact: true }).click()
  await page
    .getByRole('link', { name: new RegExp(`test-model.*${records[0].id}`) })
    .click()
  await page
    .getByTestId('selected-benchmark-run')
    .getByText(records[0].id, { exact: true })
    .waitFor()
  await page.setViewportSize({ width: 320, height: 800 })
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  )
  await context.addInitScript(() =>
    localStorage.setItem('llm-harness-language', 'en-US'),
  )
  await page.reload()
  await page
    .getByRole('heading', { name: 'Run history', exact: true })
    .waitFor()
  assert.deepEqual(errors, [])
  console.log(
    JSON.stringify({
      layer: 'real-tcp-http-browser',
      checks: 9,
      pageErrors: errors,
    }),
  )
} finally {
  await browser.close()
}
