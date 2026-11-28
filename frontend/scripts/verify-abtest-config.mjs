/* global localStorage, console, document, window */
import process from 'node:process'
import { URL } from 'node:url'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.ABTEST_QA_BASE_URL || 'http://127.0.0.1:5197'
const output = process.env.ABTEST_QA_DIR || '/tmp/issue527-browser'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : { channel: 'chrome' }),
})
const checks = []
let activePage
try {
  for (const language of ['zh-CN', 'en-US']) {
    const context = await browser.newContext({
      viewport: { width: 1366, height: 1000 },
    })
    await context.addInitScript((language) => {
      localStorage.setItem(
        'llm-harness-session',
        JSON.stringify({
          marker: 'abtest-qa',
          username: 'qa',
          expiresAt: Date.now() + 3600000,
        }),
      )
      localStorage.setItem('llm-harness-language', language)
    }, language)
    const page = await context.newPage()
    activePage = page
    const errors = [],
      submissions = []
    page.on('pageerror', (error) => errors.push(error.message))
    let saved, releaseFailure, notifyCreate
    const firstCreate = new Promise((resolve) => {
      notifyCreate = resolve
    })
    await context.route('**/api/v1/**', async (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname.replace('/api/v1', '')
      let data
      if (path === '/api-keys')
        data = [
          {
            id: 'key-qa',
            provider: 'openai',
            key_name: 'QA key',
            created_at: 1700000000,
            last_used_at: null,
            usage_count: 0,
            verified: true,
            masked_preview: null,
          },
        ]
      else if (path === '/datasets')
        data = [
          {
            id: 'dataset-qa',
            name: 'QA',
            problem_count: 6,
            updated_at: 1795737600,
          },
        ]
      else if (path === '/evaluation-options')
        data = {
          strategies: [{ name: 'self_consistency' }, { name: 'vanilla' }],
          sources: [],
        }
      else if (path === '/evaluation-options/models')
        data = { provider: 'openai', models: ['offline'], complete: true }
      else if (path === '/ab-tests' && request.method() === 'POST') {
        const payload = request.postDataJSON()
        submissions.push(payload)
        if (submissions.length === 1) {
          const released = new Promise((resolve) => {
            releaseFailure = resolve
          })
          notifyCreate()
          await released
          return route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Offline retry fixture' }),
          })
        }
        saved = {
          id: 'abtest-qa',
          task_id: null,
          name: payload.name,
          status: 'pending',
          config: payload,
          error_message: null,
          created_at: '2026-11-27T00:00:00Z',
          updated_at: '2026-11-27T00:00:00Z',
        }
        data = saved
      } else if (path === '/ab-tests/abtest-qa') data = saved
      else if (path === '/users/me')
        data = {
          id: 'qa',
          username: 'qa',
          role: 'user',
          email: 'qa@example.org',
        }
      else if (path === '/notifications')
        data = { items: [], total: 0, unread_count: 0, has_more: false }
      else
        return route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Unmocked ' + path }),
        })
      return route.fulfill({
        status: path === '/ab-tests' ? 201 : 200,
        contentType: 'application/json',
        body: JSON.stringify({ data }),
      })
    })
    const zh = language === 'zh-CN'
    const label = (cn, en) => page.getByLabel(zh ? cn : en, { exact: true })
    async function select(cn, en, option) {
      await label(cn, en).click()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: option })
        .click()
    }
    await page.goto(base + '/ab-tests/new')
    await select(
      '选择个人题库',
      'Select personal library',
      zh ? '个人题库 · 6 题' : 'Personal library · 6 problems',
    )
    await select('A/B 密钥', 'A/B key', 'QA key')
    await label('A/B 模型', 'A/B model').fill('offline')
    await select('A/B 策略', 'A/B strategy', 'self_consistency')
    await label('A/B 策略温度', 'A/B strategy temperature').fill('0.25')
    await page
      .locator('summary')
      .filter({ hasText: zh ? '高级策略配置' : 'Advanced strategy settings' })
      .click()
    await label(
      '策略 1 最大生成 Token',
      'Strategy 1 maximum generation tokens',
    ).fill('3456')
    await label('策略 1 系统提示词', 'Strategy 1 system prompt').fill(
      'Strategy default instructions',
    )
    await label('策略 1 自定义参数', 'Strategy 1 custom parameters').fill(
      '{"num_candidates":0}',
    )
    await select('题目筛选难度', 'Problem filter difficulty', 'easy')
    await label('题目筛选标签', 'Problem filter tags').fill(
      'array, math\narray',
    )
    await label('题目筛选题目 ID', 'Problem filter problem IDs').fill(
      'picked-a, picked-b, picked-c',
    )
    await label('题目筛选数量上限', 'Problem filter limit').fill('2')
    await label('A/B 随机种子', 'A/B random seed').fill('17')
    await label('A/B 并行数', 'A/B concurrency').fill('2')
    await label('实验变体系统提示词', 'Experiment variant system prompt').fill(
      'Variant override',
    )
    const submit = page.getByRole('button', {
      name: zh ? '提交 A/B 测试' : 'Submit A/B test',
      exact: true,
    })
    await submit.click()
    await page
      .getByRole('alert')
      .filter({ hasText: /num_candidates/ })
      .waitFor()
    assert.equal(submissions.length, 0)
    await label('策略 1 自定义参数', 'Strategy 1 custom parameters').fill(
      '{"num_candidates":3,"temperature":1.2}',
    )
    await page.screenshot({
      path: `${output}/${language}-form.png`,
      fullPage: true,
    })
    await submit.click()
    await firstCreate
    assert.equal(await submit.isDisabled(), true)
    assert.equal(await label('A/B 模型', 'A/B model').isDisabled(), true)
    assert.equal(
      await label(
        '策略 1 自定义参数',
        'Strategy 1 custom parameters',
      ).isDisabled(),
      true,
    )
    assert.equal(submissions.length, 1)
    releaseFailure()
    await page
      .getByRole('alert')
      .filter({
        hasText: zh ? '服务暂时不可用' : 'Service is temporarily unavailable',
      })
      .waitFor()
    assert.equal(
      await label('策略 1 系统提示词', 'Strategy 1 system prompt').inputValue(),
      'Strategy default instructions',
    )
    await label(
      '策略 1 最大生成 Token',
      'Strategy 1 maximum generation tokens',
    ).fill('4000')
    await submit.click()
    await page.waitForURL('**/ab-tests/abtest-qa')
    assert.equal(submissions.length, 2)
    const payload = submissions[1]
    assert.deepEqual(payload.strategy, {
      name: 'self_consistency',
      temperature: 0.25,
      max_tokens: 4000,
      system_prompt: 'Strategy default instructions',
      custom_params: { num_candidates: 3, temperature: 1.2 },
    })
    assert.deepEqual(payload.problem_filters, {
      difficulty: 'easy',
      tags: ['array', 'math'],
      problem_ids: ['picked-a', 'picked-b', 'picked-c'],
      limit: 2,
    })
    assert.equal(payload.prompt_variants[0].id, 'baseline')
    assert.equal(payload.prompt_variants[0].system_prompt, undefined)
    assert.equal(payload.prompt_variants[1].system_prompt, 'Variant override')
    assert.equal(payload.seed, 17)
    assert.equal(payload.max_workers, 2)
    await page.reload()
    await page.getByText(/Strategy default instructions/).waitFor()
    await page.getByText(/picked-a, picked-b, picked-c/).waitFor()
    await page.screenshot({
      path: `${output}/${language}-detail.png`,
      fullPage: true,
    })
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        true,
        `overflow ${width}`,
      )
    }
    await page.screenshot({
      path: `${output}/${language}-mobile.png`,
      fullPage: true,
    })
    saved.config = { ...saved.config, strategy: { name: 'vanilla' } }
    delete saved.config.problem_filters
    await page.reload()
    await page
      .getByText(zh ? '使用现有默认配置' : 'Use existing defaults', {
        exact: true,
      })
      .waitFor()
    await page
      .getByText(zh ? '全部题目（未筛选）' : 'All problems (no filters)', {
        exact: true,
      })
      .waitFor()
    assert.deepEqual(errors, [])
    checks.push({
      language,
      payload,
      passed: [
        'invalid input blocks submission',
        'busy form disabled',
        '503 retains draft',
        'corrected resubmission',
        'strategy and filter payload',
        'variant/seed/concurrency preserved',
        'detail reload',
        '320/390px layout',
        'legacy defaults',
      ],
      pageErrors: errors,
    })
    await context.close()
  }
  await writeFile(`${output}/report.json`, JSON.stringify(checks, null, 2))
  console.log(
    JSON.stringify({
      passed: true,
      output,
      languages: checks.map((check) => check.language),
    }),
  )
} catch (error) {
  if (activePage && !activePage.isClosed()) {
    await activePage.screenshot({
      path: `${output}/failure.png`,
      fullPage: true,
    })
    await writeFile(
      `${output}/failure.txt`,
      await activePage.locator('body').innerText(),
    )
  }
  throw error
} finally {
  await browser.close()
}
