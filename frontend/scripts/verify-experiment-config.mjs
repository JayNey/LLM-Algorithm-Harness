/* global localStorage, console */
import process from 'node:process'
import { URL } from 'node:url'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.EXPERIMENT_QA_BASE_URL || 'http://127.0.0.1:5196'
const output = process.env.EXPERIMENT_QA_DIR || '/tmp/issue526-browser'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
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
          marker: 'experiment-qa',
          username: 'qa',
          expiresAt: Date.now() + 3600000,
        }),
      )
      localStorage.setItem('llm-harness-language', language)
    }, language)
    const page = await context.newPage()
    activePage = page
    const pageErrors = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    let saved
    const submissions = []
    await context.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace('/api/v1', '')
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
      else if (path === '/experiments' && route.request().method() === 'POST') {
        const payload = route.request().postDataJSON()
        submissions.push(payload)
        saved = {
          id: 'experiment-qa',
          task_id: null,
          name: payload.name,
          status: 'pending',
          config: payload,
          error_message: null,
          created_at: '2026-11-27T00:00:00Z',
          updated_at: '2026-11-27T00:00:00Z',
        }
        data = saved
      } else if (path === '/experiments/experiment-qa') data = saved
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
      await route.fulfill({
        status: path === '/experiments' ? 201 : 200,
        contentType: 'application/json',
        body: JSON.stringify({ data }),
      })
    })
    const zh = language === 'zh-CN'
    const label = (cn, en) => page.getByLabel(zh ? cn : en, { exact: true })
    async function select(cn, en, option) {
      await label(cn, en).click()
      await page
        .locator('.ant-select-dropdown:visible')
        .locator('.ant-select-item-option-content')
        .filter({ hasText: option })
        .click()
    }
    await page.goto(base + '/experiments/new')
    await select(
      '选择个人题库',
      'Select personal library',
      zh ? '个人题库 · 6 题' : 'Personal library · 6 problems',
    )
    await select('实验 API Key', 'Experiment API key', 'QA key')
    await label('模型 1 名称', 'Model 1 name').fill('offline')
    await label('策略 1 名称', 'Strategy 1 name').fill('self_consistency')
    await page
      .locator('summary')
      .filter({ hasText: zh ? '高级策略配置' : 'Advanced strategy settings' })
      .click()
    await label(
      '策略 1 最大生成 Token',
      'Strategy 1 maximum generation tokens',
    ).fill('3456')
    await label('策略 1 系统提示词', 'Strategy 1 system prompt').fill(
      'Use the supplied instructions.',
    )
    await label('策略 1 自定义参数', 'Strategy 1 custom parameters').fill(
      '{"num_candidates":0}',
    )
    await select('实验筛选难度', 'Experiment difficulty filter', 'easy')
    await label('实验筛选标签', 'Experiment tag filters').fill(
      'array, math\narray',
    )
    await label('实验筛选题目 ID', 'Experiment problem ID filters').fill(
      'picked-a, picked-b, picked-c',
    )
    await label('实验筛选数量上限', 'Experiment problem limit').fill('2')
    for (const [kind, value] of Object.entries({
      max_calls: '1',
      max_tokens: '15',
      max_seconds: '0.1',
    }))
      await label(`实验预算 ${kind}`, `Experiment budget ${kind}`).fill(value)
    const submit = page.getByRole('button', {
      name: zh ? '提交实验' : 'Submit experiment',
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
    await page.waitForURL('**/experiments/experiment-qa')
    assert.equal(submissions.length, 1)
    const payload = submissions[0]
    assert.deepEqual(payload.strategies, [
      {
        name: 'self_consistency',
        max_tokens: 3456,
        system_prompt: 'Use the supplied instructions.',
        custom_params: { num_candidates: 3, temperature: 1.2 },
      },
    ])
    assert.deepEqual(payload.problem_filters, {
      difficulty: 'easy',
      tags: ['array', 'math'],
      problem_ids: ['picked-a', 'picked-b', 'picked-c'],
      limit: 2,
    })
    assert.deepEqual(payload.budget, {
      max_calls: 1,
      max_tokens: 15,
      max_seconds: 0.1,
    })
    await page.reload()
    await page
      .getByText('Use the supplied instructions.', { exact: false })
      .waitFor()
    await page.getByText(/picked-a, picked-b, picked-c/).waitFor()
    await page.screenshot({
      path: `${output}/${language}-detail.png`,
      fullPage: true,
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({
      path: `${output}/${language}-mobile-detail.png`,
      fullPage: true,
    })
    // Legacy responses omit advanced fields and filters entirely.
    saved.config = {
      ...saved.config,
      strategies: [{ name: 'vanilla' }],
      budget: null,
    }
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
    assert.deepEqual(pageErrors, [])
    checks.push({
      language,
      payload,
      passed: [
        'invalid custom parameters blocked; correction retained',
        'combined budget and filters submitted',
        'advanced fields preserved',
        'detail reload displays saved configuration',
        'mobile detail rendered without runtime errors',
        'legacy task defaults and unfiltered scope displayed',
      ],
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
