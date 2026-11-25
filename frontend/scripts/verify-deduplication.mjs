/* global localStorage, document */
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import process from 'node:process'
import { URL } from 'node:url'
import { setTimeout } from 'node:timers'

const base = process.env.PROBLEM_BASE_URL || 'http://127.0.0.1:5180'
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
let page
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
  })
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
  const a = {
    problem_id: 'a',
    title: 'Search A',
    description: 'Original A',
    tags: ['array'],
    source_platform: 'leetcode',
    source_problem_id: '1',
  }
  const b = {
    ...a,
    problem_id: 'b',
    title: 'Search B',
    description: 'Keep B',
    tags: ['search'],
  }
  const group = {
    group_id: 'g',
    recommended_primary_id: 'a',
    problems: [a, b],
    matches: [
      { left_id: 'a', right_id: 'b', fingerprint: true, similarity: 0.95 },
    ],
    merges: {
      a: { ...a, tags: ['array', 'search'], merged_from: ['b'] },
      b: { ...b, tags: ['search', 'array'], merged_from: ['a'] },
    },
  }
  let mode = 'ready'
  let saves = []
  let releaseScan
  await context.route('**/api/v1/**', async (route, request) => {
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const reply = (data, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({
          success: status < 400,
          data,
          message: '',
          detail: status === 409 ? 'stale' : '',
        }),
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
    if (path.endsWith('/deduplication/preview')) {
      if (mode === 'late')
        await new Promise((resolve) => {
          releaseScan = resolve
        })
      if (mode === 'error') return reply(null, 503)
      return reply({
        preview_token: 'preview',
        groups:
          mode === 'empty'
            ? []
            : [
                group,
                {
                  ...group,
                  group_id: 'g2',
                  problems: [a, b].map((p) => ({
                    ...p,
                    problem_id: p.problem_id + '2',
                  })),
                  recommended_primary_id: 'a2',
                  matches: [
                    {
                      left_id: 'a2',
                      right_id: 'b2',
                      fingerprint: true,
                      similarity: null,
                    },
                  ],
                  merges: {
                    a2: { ...a, problem_id: 'a2' },
                    b2: { ...b, problem_id: 'b2' },
                  },
                },
              ],
      })
    }
    if (path.endsWith('/deduplication/versions')) {
      saves.push(request.postDataJSON())
      if (mode === 'stale') return reply(null, 409)
      return reply({ id: 'v', name: 'Reviewed', problem_count: 3 }, 201)
    }
    if (path.endsWith('/governance/versions/v'))
      return reply({
        id: 'v',
        name: 'Reviewed',
        problem_count: 3,
        problems: [
          {
            problem_id: 'b',
            title: 'Search B',
            difficulty: 'easy',
            tags: ['search', 'array'],
            merged_from: ['a'],
          },
        ],
      })
    if (path.endsWith('/governance/versions'))
      return reply(
        saves.length ? [{ id: 'v', name: 'Reviewed', problem_count: 3 }] : [],
      )
    return reply([], 200)
  })
  page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => {
    errors.push(error.message)
    process.stderr.write(error.message + '\n')
  })
  await page.goto(base + '/problems')
  await page.getByRole('button', { name: '批量治理', exact: true }).click()
  await page.getByRole('tab', { name: '查找相似题', exact: true }).click()
  const scan = () => page.getByRole('button', { name: /扫描相似题/ }).click()
  await scan()
  const first = page.getByRole('group', { name: '候选组 1', exact: true })
  await first.waitFor()
  assert.equal(
    await page
      .getByRole('button', { name: '保存题集版本', exact: true })
      .isEnabled(),
    false,
  )
  await first.getByLabel('保留题').selectOption('b')
  await first.getByText('合并后的题目', { exact: true }).click()
  assert.match(await first.innerText(), /Keep B/)
  await page.screenshot({
    path: '/private/tmp/issue-474-review.png',
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(350)
  const mobileBounds = await first.boundingBox()
  assert.ok(
    mobileBounds.x >= 0 && mobileBounds.x + mobileBounds.width <= 391,
    'Review fits mobile viewport',
  )
  await page.screenshot({
    path: '/private/tmp/issue-474-mobile.png',
    fullPage: true,
  })
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page
    .getByRole('textbox', { name: '题集版本名称', exact: true })
    .fill('Reviewed')
  mode = 'stale'
  await page.getByRole('button', { name: '保存题集版本', exact: true }).click()
  await page
    .getByText('题库已更新，请重新扫描并确认。', { exact: true })
    .waitFor()
  assert.deepEqual(saves[0].groups, [{ group_id: 'g', primary_id: 'b' }])
  assert.equal(
    await page.getByRole('group', { name: '候选组 1', exact: true }).count(),
    0,
  )
  mode = 'empty'
  await scan()
  await page.getByText('没有发现相似题。', { exact: true }).waitFor()
  mode = 'error'
  await scan()
  await page
    .getByRole('button', { name: /重\s*试/ })
    .waitFor({ timeout: 5000 })
    .catch(async (error) => {
      await page.screenshot({ path: '/private/tmp/issue-474-failure.png' })
      process.stderr.write(await page.locator('.ant-drawer-body').innerText())
      throw error
    })
  mode = 'ready'
  await page.getByRole('button', { name: /重\s*试/ }).click()
  await first.waitFor()
  // Parameter changes must clear an old review before a new scan.
  await first.getByLabel('保留题').selectOption('a')
  await page
    .getByRole('spinbutton', { name: '文本相似度阈值', exact: true })
    .fill('0.8')
  assert.equal(await first.count(), 0)
  await scan()
  await first.getByLabel('保留题').selectOption('b')
  await page
    .getByRole('button', { name: '保存题集版本', exact: true })
    .dblclick()
  await page
    .getByRole('link', { name: '使用此版本创建评估', exact: true })
    .waitFor()
  assert.equal(saves.length, 2)
  assert.equal(saves[1].threshold, 0.8)
  assert.deepEqual(saves[1].groups, [{ group_id: 'g', primary_id: 'b' }])
  assert.match(
    await page
      .getByRole('link', { name: '使用此版本创建评估' })
      .getAttribute('href'),
    /dataset_version=v/,
  )
  await page.screenshot({ path: '/private/tmp/issue-474-versions.png' })
  await page.getByRole('tab', { name: '查找相似题', exact: true }).click()
  mode = 'late'
  await scan()
  await page.waitForFunction(() =>
    document.querySelector('[aria-label="文本相似度阈值"]'),
  )
  const waitForScan = async () => {
    const deadline = Date.now() + 5000
    while (!releaseScan && Date.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 10))
    assert.ok(releaseScan, 'Delayed scan started')
  }
  await waitForScan()
  await page
    .getByRole('spinbutton', { name: '文本相似度阈值', exact: true })
    .fill('0.7')
  releaseScan()
  await page.waitForTimeout(200)
  assert.equal(await first.count(), 0)
  releaseScan = undefined
  await scan()
  await waitForScan()
  await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/store/auth.ts')
    useAuthStore.setState({
      session: {
        marker: 'other-owner',
        username: 'other',
        expiresAt: Date.now() + 3600000,
      },
    })
  })
  releaseScan()
  await page.waitForTimeout(200)
  assert.equal(await first.count(), 0)
  assert.equal(
    await page
      .getByRole('link', { name: '使用此版本创建评估', exact: true })
      .count(),
    0,
  )
  assert.deepEqual(errors, [])
  process.stdout.write(
    'Passed: review, primary choice, skip, stale, empty, retry, parameter invalidation, duplicate click, navigation, late scan.\n',
  )
} catch (error) {
  if (page) {
    await page.screenshot({ path: '/private/tmp/issue-474-failure.png' })
    process.stderr.write(await page.locator('body').innerText())
  }
  throw error
} finally {
  await browser.close()
}
