import assert from 'node:assert/strict'
import { URL } from 'node:url'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import process from 'node:process'
import console from 'node:console'

// Issue #329: the real results pages against a seeded real API; no route stubs.
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.ANALYTICS_UI_URL
const api = process.env.ANALYTICS_API_URL
const expected = JSON.parse(process.env.ANALYTICS_EXPECTED || 'null')
assert.ok(
  base &&
    api &&
    expected &&
    process.env.ANALYTICS_USERNAME &&
    process.env.ANALYTICS_PASSWORD &&
    process.env.ANALYTICS_EVALUATION_ID,
)
for (const origin of [base, api])
  assert.equal(new URL(origin).hostname, '127.0.0.1')
const browser = await chromium.launch({
  headless: true,
  channel: process.env.ANALYTICS_BROWSER_CHANNEL,
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
    requests.push({
      method: request.method(),
      path: url.pathname.replace('/api/v1', ''),
      query: url.search,
    })
})
const analyticsPath = (call) =>
  /^\/(analytics|visualizations|failures|compare)\//.test(call.path)
const pair = ([solved, total]) => `${solved} / ${total}`
async function rowText(table, name) {
  return table
    .locator('tbody tr')
    .filter({ has: page.getByRole('cell', { name, exact: true }) })
    .first()
    .innerText()
}
try {
  await page.goto(base + '/login')
  await page.locator('#login-identity').fill(process.env.ANALYTICS_USERNAME)
  await page.locator('#login-password').fill(process.env.ANALYTICS_PASSWORD)
  await page.getByRole('button', { name: /登\s*录/, exact: true }).click()
  await page.waitForURL(base + '/')
  checks.push('real cookie login')

  await page.goto(
    `${base}/results/${encodeURIComponent(process.env.ANALYTICS_EVALUATION_ID)}`,
  )
  const section = page.getByRole('region', { name: '结果分析', exact: true })
  const stats = section.getByRole('region', { name: '成功率统计', exact: true })
  await stats
    .getByText(
      new RegExp(
        `成功 ${expected.success_rate.solved} \\/ ${expected.success_rate.total}`,
      ),
    )
    .waitFor()
  const byTag = stats.getByRole('table', { name: '按标签成功率', exact: true })
  for (const [tag, bucket] of Object.entries(expected.by_tag))
    assert.ok((await rowText(byTag, tag)).includes(pair(bucket)), tag)
  assert.equal(
    await byTag.getByRole('cell', { name: 'graph', exact: true }).count(),
    0,
  )
  const byDifficulty = stats.getByRole('table', {
    name: '按难度成功率',
    exact: true,
  })
  for (const [difficulty, bucket] of Object.entries(expected.by_difficulty))
    assert.ok(
      (await rowText(byDifficulty, difficulty)).includes(pair(bucket)),
      difficulty,
    )
  assert.ok(
    requests
      .filter(analyticsPath)
      .every((call) => call.query.includes(`run_id=`)),
  )
  checks.push(
    'stats panels use real run-scoped analytics; snapshot tags beat the public row, empty tags excluded',
  )
  const tokens = section.getByRole('region', {
    name: 'Token 与费用',
    exact: true,
  })
  const tokensText = await tokens.innerText()
  assert.ok(
    tokensText.includes(`${expected.tokens.unknown_cost_count} 条成本未知`),
    tokensText,
  )
  assert.ok(tokensText.includes('下限'), tokensText)
  checks.push('unknown cost shown as a lower bound')

  await page.getByRole('tab', { name: /图表$/ }).click()
  const radar = section
    .getByRole('region', { name: '能力雷达', exact: true })
    .getByRole('table', { name: '能力雷达', exact: true })
  await radar.waitFor()
  for (const [dimension, [score, count]] of Object.entries(expected.radar)) {
    const cells = await radar
      .locator('tbody tr')
      .filter({ has: page.getByRole('cell', { name: dimension, exact: true }) })
      .first()
      .locator('td')
      .allInnerTexts()
    assert.deepEqual(
      cells.slice(0, 3),
      [dimension, String(count), String(score)],
      dimension,
    )
  }
  checks.push(
    'capability radar table matches server dimension scores and problem counts',
  )

  await page.getByRole('tab', { name: /失败分析$/ }).click()
  const cases = section.getByRole('region', { name: '失败案例', exact: true })
  await cases
    .getByText(`共 ${expected.failure_cases} 条非成功单元。`, { exact: true })
    .waitFor()
  const casesText = await cases.innerText()
  assert.ok(
    casesText.includes('assert 1 == 2') && casesText.includes('未记录'),
    casesText,
  )
  const summaryText = await section
    .getByRole('region', { name: '失败摘要', exact: true })
    .innerText()
  for (const [mode, count] of Object.entries(expected.failure_modes))
    assert.ok(
      summaryText.includes(mode) && summaryText.includes(String(count)),
      mode,
    )
  assert.ok(summaryText.includes(expected.clusters[0].pattern), summaryText)
  assert.equal(
    requests.find((call) => call.path.startsWith('/failures/summary/'))?.query,
    '',
  )
  checks.push('failure summary and cases are traceable to seeded units')

  await page.getByRole('tab', { name: /对比$/ }).click()
  const strategies = section
    .getByRole('region', { name: '策略对比', exact: true })
    .getByRole('table', { name: '策略对比', exact: true })
  await strategies.waitFor()
  for (const [name, bucket] of Object.entries(expected.strategies))
    assert.ok((await rowText(strategies, name)).includes(pair(bucket)), name)
  const history = section.getByRole('region', { name: '历史对比', exact: true })
  for (const runId of expected.history_run_ids)
    await history.getByText(runId, { exact: true }).waitFor()
  const historyText = await history.innerText()
  assert.ok(!historyText.includes('f3-other-id'), historyText)
  assert.ok(historyText.includes('同模型且策略集合相同'), historyText)
  checks.push(
    'strategy and history comparison match the API and label their scope',
  )

  await page.goto(base + '/results')
  await page.getByRole('table', { name: '评估结果列表', exact: true }).waitFor()
  const before = requests.length
  await page
    .getByRole('button', { name: '查看全账号分析', exact: true })
    .click()
  const account = page.getByRole('region', { name: '全账号分析', exact: true })
  await account.getByRole('tab', { name: /模型对比$/ }).click()
  const models = account
    .getByRole('region', { name: '模型对比', exact: true })
    .getByRole('table', { name: '模型对比', exact: true })
  await models.waitFor()
  const modelsText = await models.innerText()
  for (const model of expected.models)
    assert.ok(modelsText.includes(model), model)
  const modelCalls = requests.filter((call) => call.path === '/compare/models')
  assert.equal(modelCalls.length, 1)
  assert.equal(modelCalls[0].query, '')
  assert.ok(
    requests
      .slice(before)
      .filter(analyticsPath)
      .every((call) => !call.query.includes('run_id')),
  )
  checks.push(
    'account analysis is on demand, unscoped and lists every completed model',
  )
  assert.deepEqual(errors, [])
  assert.ok(requests.filter(analyticsPath).length > 0)
  passed = true
} finally {
  await writeFile(
    process.env.ANALYTICS_OUT,
    JSON.stringify(
      {
        passed,
        checks,
        errors,
        analyticsRequests: requests.filter(analyticsPath),
      },
      null,
      2,
    ),
  )
  console.log(JSON.stringify({ passed, checks: checks.length, errors }))
  await browser.close()
}
if (!passed) process.exit(1)
