/* global localStorage, document, console */
import process from 'node:process'
import { URL } from 'node:url'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'
const output = '/tmp/issue528-browser'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const checks = []
try {
  for (const language of ['zh-CN', 'en-US']) {
    const context = await browser.newContext({
      viewport: { width: 1366, height: 1000 },
    })
    await context.addInitScript((language) => {
      localStorage.setItem(
        'llm-harness-session',
        JSON.stringify({
          marker: 'qa',
          username: 'qa',
          expiresAt: Date.now() + 3600000,
        }),
      )
      localStorage.setItem('llm-harness-language', language)
    }, language)
    const page = await context.newPage(),
      submissions = [],
      errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    const suite = {
      id: 'suite-qa',
      name: 'QA suite',
      version: '1.0',
      description: null,
      frozen: true,
      problems: ['b', 'a'],
      created_at: '2026-11-28T00:00:00Z',
      updated_at: '2026-11-28T00:00:00Z',
    }
    const old = {
      id: 'old-run',
      suite_id: suite.id,
      task_id: null,
      status: 'completed',
      model: 'legacy-model',
      accuracy: 0.5,
      cost_usd: 0.01,
      error_message: null,
      created_at: suite.created_at,
      updated_at: suite.updated_at,
    }
    let saved
    await context.route('**/api/v1/**', async (route) => {
      const req = route.request(),
        url = new URL(req.url()),
        path = url.pathname.replace('/api/v1', '')
      let data,
        status = 200
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
      else if (path === '/users/me')
        data = {
          id: 'qa',
          username: 'qa',
          role: 'user',
          email: 'qa@example.org',
        }
      else if (path === '/notifications')
        data = { items: [], total: 0, unread_count: 0, has_more: false }
      else if (path === '/benchmarks/suites/suite-qa') data = suite
      else if (path === '/benchmarks/learning-curve/suite-qa')
        data = {
          suite_id: suite.id,
          suite_name: suite.name,
          data: [],
          trends: { accuracy_growth_rate: null, cost_growth_rate: null },
        }
      else if (path === '/benchmarks/suites/suite-qa/runs') {
        const items = url.searchParams.has('status')
          ? []
          : [...(saved ? [saved] : []), old]
        data = {
          items,
          total: items.length,
          limit: Number(url.searchParams.get('limit') || 20),
          offset: 0,
          has_more: false,
        }
      } else if (
        path === '/benchmarks/suites/suite-qa/run' &&
        req.method() === 'POST'
      ) {
        submissions.push(req.postDataJSON())
        saved = {
          ...old,
          id: 'new-run',
          task_id: 'task-qa',
          model: 'offline',
          accuracy: 1,
          cost_usd: 0.02,
          results: { problems_evaluated: 1 },
        }
        data = saved
        status = 202
      } else if (path === '/benchmarks/runs/new-run') data = saved
      else if (path === '/benchmarks/runs/old-run') data = old
      else if (path === '/tasks/task-qa')
        data = {
          id: 'task-qa',
          task_type: 'benchmark',
          entity_id: 'new-run',
          status: 'completed',
          progress: {
            current: 1,
            total: 1,
            percentage: 100,
            current_step: 'done',
          },
          error_message: null,
        }
      else
        return route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Unmocked ' + path }),
        })
      return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ data }),
      })
    })
    const zh = language === 'zh-CN',
      label = (cn, en) => page.getByLabel(zh ? cn : en, { exact: true })
    async function select(cn, en, option) {
      await label(cn, en).click()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: option })
        .click()
    }
    await page.goto(
      (process.env.BENCHMARK_QA_BASE_URL || 'http://127.0.0.1:5198') +
        '/benchmarks/suite-qa',
    )
    await page.getByText('legacy-model', { exact: true }).waitFor()
    await select(
      '选择个人题库',
      'Select personal library',
      zh ? '个人题库 · 6 题' : 'Personal library · 6 problems',
    )
    await select('基准运行密钥', 'Benchmark run key', 'QA key')
    await label('基准运行模型', 'Benchmark run model').fill('offline')
    await select('基准运行策略', 'Benchmark run strategies', 'self_consistency')
    await label('策略 1 最大迭代次数', 'Strategy 1 max iterations').fill('3')
    await label('策略 1 温度', 'Strategy 1 temperature').fill('0')
    await page
      .locator('summary')
      .filter({ hasText: zh ? '高级策略配置' : 'Advanced strategy settings' })
      .click()
    await label(
      '策略 1 最大生成 Token',
      'Strategy 1 maximum generation tokens',
    ).fill('3456')
    await label('策略 1 系统提示词', 'Strategy 1 system prompt').fill(
      'Follow these instructions.',
    )
    await label('策略 1 自定义参数', 'Strategy 1 custom parameters').fill(
      '{"num_candidates":0}',
    )
    await select('题目筛选难度', 'Problem filter difficulty', 'easy')
    await label('题目筛选标签', 'Problem filter tags').fill(
      'array, math\narray',
    )
    await label('题目筛选题目 ID', 'Problem filter problem IDs').fill('a,b')
    await label('题目筛选数量上限', 'Problem filter limit').fill('0')
    const submit = page.getByRole('button', {
      name: zh ? '启动基准运行' : 'Start benchmark run',
      exact: true,
    })
    await submit.click()
    await page
      .getByRole('alert')
      .filter({
        hasText: zh
          ? '题目数量上限须为正整数'
          : 'Problem limit must be a positive integer',
      })
      .waitFor()
    assert.equal(submissions.length, 0)
    await label('题目筛选数量上限', 'Problem filter limit').fill('1')
    await label('策略 1 自定义参数', 'Strategy 1 custom parameters').fill(
      '{"num_candidates":3,"temperature":1.2}',
    )
    await submit.click()
    await page.waitForURL(/run_id=new-run/)
    assert.deepEqual(submissions[0], {
      api_key_id: 'key-qa',
      dataset_id: 'dataset-qa',
      model: 'offline',
      strategies: [
        {
          name: 'self_consistency',
          max_iterations: 3,
          temperature: 0,
          max_tokens: 3456,
          system_prompt: 'Follow these instructions.',
          custom_params: { num_candidates: 3, temperature: 1.2 },
        },
      ],
      problem_filters: {
        difficulty: 'easy',
        tags: ['array', 'math'],
        problem_ids: ['a', 'b'],
        limit: 1,
      },
    })
    await page.getByText('legacy-model', { exact: true }).waitFor()
    await page.screenshot({
      path: `${output}/${language}-desktop.png`,
      fullPage: true,
    })
    await page.setViewportSize({ width: 320, height: 900 })
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= 320),
      'no page-wide overflow',
    )
    await page.screenshot({
      path: `${output}/${language}-mobile.png`,
      fullPage: true,
    })
    assert.deepEqual(errors, [])
    checks.push({
      language,
      payload: submissions[0],
      legacyHistory: true,
      mobile: true,
      errors,
    })
    await context.close()
  }
  await writeFile(`${output}/checks.json`, JSON.stringify(checks, null, 2))
  console.log(
    'Passed: bilingual form, invalid input, complete request, legacy history, 320px layout',
  )
} finally {
  await browser.close()
}
