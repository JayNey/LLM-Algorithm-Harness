/* global document, fetch, setTimeout */
import assert from 'node:assert/strict'
import process from 'node:process'
import console from 'node:console'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { pathToFileURL, URL } from 'node:url'
import { execFileSync } from 'node:child_process'

export function localOrigin(value) {
  const url = new URL(value)
  assert.ok(['http:', 'https:'].includes(url.protocol))
  assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))
  assert.ok(!url.username && !url.password && url.pathname === '/')
  return url.origin
}

export function budgetBound(allowed, promptTokens, outputTokens, attempts) {
  assert.ok(Number.isFinite(allowed) && allowed > 0 && allowed <= 0.1)
  assert.ok(
    Number.isInteger(promptTokens) && promptTokens > 0 && promptTokens <= 16384,
  )
  assert.ok(
    Number.isInteger(outputTokens) && outputTokens > 0 && outputTokens <= 2000,
  )
  assert.ok(Number.isInteger(attempts) && attempts > 0 && attempts <= 2)
  // Conservative peak cache-miss USD prices, per million tokens, checked 2026-10-27.
  const bound =
    (attempts * (promptTokens * 0.3 + outputTokens * 1.2)) / 1_000_000
  assert.ok(bound <= allowed)
  return bound
}

export function publicId(value) {
  return value == null
    ? null
    : `sha256:${createHash('sha256').update(String(value)).digest('hex').slice(0, 16)}`
}

function selfTest() {
  assert.equal(localOrigin('http://localhost:3000'), 'http://localhost:3000')
  assert.throws(() => localOrigin('https://example.org'))
  assert.throws(() => localOrigin('http://user:password@localhost:3000'))
  assert.ok(budgetBound(0.1, 16384, 2000, 2) < 0.1)
  assert.throws(() => budgetBound(0.001, 16384, 2000, 2))
  assert.throws(() => budgetBound(NaN, 100, 2000, 2))
  assert.throws(() => budgetBound(0.1, 100, 2001, 2))
  assert.throws(() => budgetBound(0.1, 100, 2000, 3))
  assert.equal(publicId('private-id'), publicId('private-id'))
  assert.equal(publicId(null), null)
  assert.ok(!publicId('private-id').includes('private-id'))
  console.log('PASS: 11 live origin, budget and identifier guards')
}

const promptPreflight = `
import json, os
from pathlib import Path
from dotenv import load_dotenv
root=Path(os.environ['LIVE_RUNTIME_DIR'])
load_dotenv(root/'services.env',override=True)
from api.auth.config import AuthSettings
from api.auth.service import AuthService
from api.db.engine import business_database_url,make_engine,make_session_factory
from api.db.problem_store import ProblemStore
from src.tasks.evaluation import _to_domain_problem
from src.models import StrategyConfig,SandboxConfig
from src.llm_client import LLMClient
from src.sandbox_executor import SandboxExecutor
from src.strategies.vanilla import VanillaStrategy
creds=json.loads((root/'credentials.json').read_text())
auth=AuthService(AuthSettings())
user=auth.store.find_user(creds['username'])
keys=auth.store.keys(user['id'])
assert len(keys)==1 and keys[0]['provider']=='deepseek'
config=auth.llm_config(keys[0]['id'],user['id'],'deepseek-flash')
assert config.enable_thinking is False and config.max_tokens<=2000
assert auth.settings.USER_DAILY_API_CALL_LIMIT==2 and auth.settings.USER_MONTHLY_API_CALL_LIMIT==2
engine=make_engine(business_database_url())
problem=_to_domain_problem(ProblemStore(make_session_factory(engine)).get_by_problem_id('live232-add'))
client=LLMClient(config)
strategy=VanillaStrategy(StrategyConfig(name='vanilla'),client,SandboxExecutor(SandboxConfig()))
prompt=strategy.build_base_prompt(problem)
print('LIVE_PLAN='+json.dumps({'prompt_bytes':len(prompt.encode()),'output_tokens':config.max_tokens,'attempts':2,'thinking':False}))
client.client.close()
engine.dispose()
`

async function run() {
  const runtime = resolve(process.env.LIVE_RUNTIME_DIR || '')
  assert.ok(process.env.LIVE_RUNTIME_DIR, 'LIVE_RUNTIME_DIR is required')
  const privatePath = join(runtime, 'credentials.json')
  assert.equal((await stat(privatePath)).mode & 0o077, 0)
  const credentials = JSON.parse(await readFile(privatePath, 'utf8'))
  const configured = JSON.parse(
    await readFile(credentials.project_config, 'utf8'),
  ).llm_config
  assert.equal(new URL(configured.base_url).hostname, 'api.deepseek.com')
  assert.equal(configured.model, 'deepseek-flash')
  const allowed = Number(credentials.budget_usd)
  const origin = localOrigin(process.env.LIVE_UI_URL || 'http://localhost:3000')
  const modulePath = process.env.PLAYWRIGHT_MODULE
  assert.ok(modulePath, 'PLAYWRIGHT_MODULE is required')
  const { chromium } = await import(pathToFileURL(resolve(modulePath)).href)
  const out = resolve(
    process.env.LIVE_QA_DIR || '../docs/frontend/assets/evaluations/live',
  )
  await mkdir(out, { recursive: true })
  const stamp = new Date()
    .toISOString()
    .replace(/[^0-9]/g, '')
    .slice(0, 17)
  const report = {
    layer:
      'real browser + FastAPI + SQLite + Redis/Celery + provider + Docker sandbox',
    replaced: [],
    started_at: new Date().toISOString(),
    source: {
      head: execFileSync('git', ['rev-parse', 'HEAD'], {
        encoding: 'utf8',
      }).trim(),
    },
    authorization: {
      provider: 'deepseek',
      model: 'deepseek-flash',
      budget_usd: allowed,
    },
    requests: [],
    snapshots: [],
    sockets: [],
    page_errors: [],
    pass: false,
  }
  let phase = 'browser-start'
  const statePath = join(runtime, 'browser-state.json')
  let state = {}
  try {
    state = JSON.parse(await readFile(statePath, 'utf8'))
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const saveState = () =>
    writeFile(statePath, JSON.stringify(state), { mode: 0o600 })
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROME_PATH ||
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  })
  const page = await context.newPage()
  page.setDefaultTimeout(20_000)
  const safePath = (path) =>
    path.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, (id) => publicId(id))
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/'))
      report.requests.push({
        utc: new Date().toISOString(),
        method: response.request().method(),
        path: safePath(url.pathname),
        status: response.status(),
      })
  })
  page.on('pageerror', (error) =>
    report.page_errors.push({
      utc: new Date().toISOString(),
      type: error.name,
    }),
  )
  page.on('websocket', (socket) => {
    const url = new URL(socket.url())
    if (!url.pathname.endsWith('/ws/progress')) return
    const observed = {
      path: url.pathname,
      token_in_url: url.searchParams.has('token'),
      received_types: [],
    }
    report.sockets.push(observed)
    socket.on('framereceived', (frame) => {
      try {
        const data = JSON.parse(String(frame.payload))
        if (typeof data.type === 'string' && /^[a-z_.]+$/.test(data.type))
          observed.received_types.push(data.type)
      } catch {
        /* Binary or malformed payloads are not published. */
      }
    })
  })
  const api = async (path, method = 'GET', body) => {
    const response = await page.evaluate(
      async ({ path, method, body }) => {
        const csrf = document.cookie
          .split('; ')
          .find((part) => part.startsWith('harness_csrf='))
          ?.split('=')
          .slice(1)
          .join('=')
        const response = await fetch('/api/v1' + path, {
          method,
          credentials: 'include',
          headers: {
            ...(body ? { 'Content-Type': 'application/json' } : {}),
            ...(method !== 'GET' && csrf
              ? { 'X-CSRF-Token': decodeURIComponent(csrf) }
              : {}),
          },
          ...(body ? { body: JSON.stringify(body) } : {}),
        })
        return { status: response.status, data: await response.json() }
      },
      { path, method, body },
    )
    assert.ok(
      response.status >= 200 && response.status < 300,
      `HTTP status ${response.status}`,
    )
    return response.data.data
  }
  const choose = async (name, text) => {
    await page.getByRole('combobox', { name, exact: true }).click()
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option')
      .filter({ hasText: text })
      .click()
    await page.keyboard.press('Escape')
  }
  try {
    if (!state.registered) {
      phase = 'real-registration'
      await page.goto(origin + '/register')
      await page.locator('#register-username').fill(credentials.username)
      await page.locator('#register-email').fill(credentials.email)
      await page.locator('#register-password').fill(credentials.password)
      await page
        .locator('#register-confirm-password')
        .fill(credentials.password)
      const [response] = await Promise.all([
        page.waitForResponse(
          (r) =>
            r.url().endsWith('/auth/register') &&
            r.request().method() === 'POST',
        ),
        page.getByRole('button', { name: /^注\s*册$/ }).click(),
      ])
      assert.equal(response.status(), 201)
      await page.waitForURL((url) => url.pathname === '/login')
      state.registered = true
      await saveState()
    }
    phase = 'real-login'
    await page.goto(origin + '/login')
    await page.locator('#login-identity').fill(credentials.username)
    await page.locator('#login-password').fill(credentials.password)
    const [loggedIn] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().endsWith('/auth/login') && r.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /^登\s*录$/ }).click(),
    ])
    assert.equal(loggedIn.status(), 200)
    await page.waitForURL((url) => url.pathname === '/')
    const cookies = await context.cookies()
    report.authentication = {
      access_http_only: cookies.some(
        (c) => c.name === 'harness_access_token' && c.httpOnly,
      ),
      refresh_http_only: cookies.some(
        (c) => c.name === 'harness_refresh_token' && c.httpOnly,
      ),
      csrf_present: cookies.some(
        (c) => c.name === 'harness_csrf' && !c.httpOnly,
      ),
    }
    assert.ok(Object.values(report.authentication).every(Boolean))
    if (!state.keyId) {
      phase = 'save-owned-provider-key'
      await page.goto(origin + '/settings/api-keys')
      await page
        .getByRole('heading', { name: 'API 密钥', exact: true })
        .waitFor()
      const form = page.locator('form')
      await form.getByRole('combobox').click()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option')
        .filter({ hasText: /^deepseek$/ })
        .click()
      await form
        .locator('input[type="text"]:not([role="combobox"])')
        .fill('Live QA DeepSeek')
      await form.locator('input[type="password"]').fill(configured.api_key)
      const [response] = await Promise.all([
        page.waitForResponse(
          (r) =>
            r.url().endsWith('/api-keys') && r.request().method() === 'POST',
        ),
        form.getByRole('button', { name: /^添\s*加$/ }).click(),
      ])
      assert.equal(response.status(), 201)
      state.keyId = (await response.json()).data.id
      await saveState()
    }
    phase = 'pricing-and-prompt-budget-preflight'
    await api('/pricing/deepseek-flash', 'POST', {
      prompt_per_1k: 0.0003,
      completion_per_1k: 0.0012,
    })
    const planOutput = execFileSync(
      process.env.LIVE_PYTHON || 'python3',
      ['-c', promptPreflight],
      {
        cwd: resolve('..'),
        env: { ...process.env, LIVE_RUNTIME_DIR: runtime },
        encoding: 'utf8',
      },
    )
    const plan = JSON.parse(
      planOutput
        .split('\n')
        .find((line) => line.startsWith('LIVE_PLAN='))
        .slice(10),
    )
    const bound = budgetBound(
      allowed,
      plan.prompt_bytes + 256,
      plan.output_tokens,
      plan.attempts,
    )
    report.budget = {
      ...plan,
      prompt_token_upper_bound: plan.prompt_bytes + 256,
      conservative_total_upper_bound_usd: bound,
      pricing_source: 'official peak cache-miss prices, 2026-10-27',
    }
    const resuming = Boolean(state.evaluationId)
    if (!state.submissionAttempted) {
      phase = 'actual-options-and-models'
      await page.goto(origin + '/evaluations/new')
      await page
        .getByRole('heading', { name: '创建评估', exact: true })
        .waitFor()
      const [modelResponse] = await Promise.all([
        page.waitForResponse((r) =>
          r.url().includes('/evaluation-options/models'),
        ),
        choose('API 密钥', /^Live QA DeepSeek · deepseek$/),
      ])
      assert.equal(modelResponse.status(), 200)
      const listed = (await modelResponse.json()).data
      assert.equal(listed.provider, 'deepseek')
      assert.ok(listed.models.includes('deepseek-flash'))
      report.models = {
        source: listed.source,
        provider: listed.provider,
        configured_model_present: true,
        complete: listed.complete,
      }
      await choose('模型', /^deepseek-flash$/)
      await choose('策略', /^vanilla$/)
      await page
        .getByRole('checkbox', { name: '选择题目 live232-add', exact: true })
        .check()
      await page.locator('#evaluation-budget').fill(String(allowed))
      state.submissionAttempted = true
      await saveState()
      phase = 'real-create-and-start'
      const [response] = await Promise.all([
        page.waitForResponse(
          (r) =>
            new URL(r.url()).pathname === '/api/v1/evaluations' &&
            r.request().method() === 'POST',
        ),
        page.getByRole('button', { name: '创建并启动', exact: true }).click(),
      ])
      assert.equal(response.status(), 201)
      state.evaluationId = (await response.json()).data.evaluation_id
      await saveState()
    }
    assert.ok(
      state.evaluationId,
      'Creation was attempted without a confirmed ID; inspect the private database before retrying',
    )
    if (resuming) await page.goto(origin + '/evaluations/' + state.evaluationId)
    phase = 'real-progress-and-terminal-state'
    await page.waitForURL(
      (url) => url.pathname === '/evaluations/' + state.evaluationId,
    )
    const deadline = Date.now() + 180_000
    let terminal
    while (Date.now() < deadline) {
      const snapshot = await api('/evaluations/' + state.evaluationId)
      report.snapshots.push({
        utc: new Date().toISOString(),
        status: snapshot.status,
        progress: snapshot.execution_progress,
        spent_usd: snapshot.spent_usd,
      })
      if (
        ['completed', 'failed', 'cancelled', 'paused'].includes(snapshot.status)
      ) {
        terminal = snapshot
        break
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    assert.equal(terminal?.status, 'completed')
    assert.equal(terminal.execution_progress.completed_units, 1)
    assert.equal(terminal.execution_progress.total_units, 1)
    assert.ok(terminal.spent_usd > 0 && terminal.spent_usd <= allowed)
    const tasks = await api('/tasks?task_type=evaluation&limit=20')
    const task = tasks.items.find(
      (item) => item.entity_id === state.evaluationId,
    )
    assert.ok(task && task.id !== state.evaluationId)
    assert.equal(task.status, 'completed')
    assert.ok(task.started_at && task.completed_at)
    report.ids = {
      evaluation: publicId(state.evaluationId),
      async_task: publicId(task.id),
      celery_task: publicId(task.celery_task_id),
      run: null,
    }
    report.worker = {
      status: task.status,
      started_at: task.started_at,
      completed_at: task.completed_at,
      entity_link_matches: true,
    }
    phase = 'real-results-page'
    await page.goto(origin + '/results/' + state.evaluationId)
    await page
      .getByRole('status', { name: '结果可用性', exact: true })
      .getByText('结果完整', { exact: true })
      .waitFor()
    const result = await api('/results/' + state.evaluationId)
    report.ids.run = publicId(result.run_id)
    assert.equal(result.problems.total, 1)
    assert.equal(result.strategies[0].solved_problems, 1)
    assert.ok(result.strategies[0].avg_tokens > 0)
    report.result = {
      status: result.status,
      recorded_units: result.problems.total,
      solved_units: result.strategies[0].solved_problems,
      average_tokens: result.strategies[0].avg_tokens,
      cost_usd: terminal.spent_usd,
      model: terminal.model,
    }
    assert.equal(report.page_errors.length, 0)
    assert.ok(
      report.requests.some(
        (r) => r.path.endsWith('/start') && r.status === 202,
      ),
    )
    assert.ok(
      report.sockets.some(
        (s) => !s.token_in_url && s.received_types.length > 0,
      ),
    )
    const masks = [
      credentials.username,
      credentials.email,
      state.evaluationId,
      task.id,
      task.celery_task_id,
      result.run_id,
    ]
      .filter(Boolean)
      .map((value) => page.getByText(String(value), { exact: false }))
    const screenshot = `run-${stamp}-result.png`
    await page.screenshot({
      path: join(out, screenshot),
      fullPage: true,
      mask: masks,
      maskColor: '#e4e4e7',
    })
    report.screenshot = screenshot
    report.pass = true
  } catch (error) {
    report.failure = { phase, type: error.name }
    // Playwright error strings may echo fill values. Keep diagnostics private.
    await writeFile(
      join(runtime, `failure-${stamp}.txt`),
      String(error.stack),
      { mode: 0o600 },
    )
  } finally {
    await browser.close()
    report.finished_at = new Date().toISOString()
    await writeFile(
      join(out, `run-${stamp}.json`),
      JSON.stringify(report, null, 2) + '\n',
    )
    console.log(
      JSON.stringify({
        pass: report.pass,
        failure: report.failure,
        evidence: `run-${stamp}.json`,
      }),
    )
  }
  if (!report.pass) process.exitCode = 1
}

if (process.argv.includes('--self-test')) selfTest()
else
  await run().catch((error) => {
    console.error(
      JSON.stringify({ pass: false, phase: 'configuration', type: error.name }),
    )
    process.exitCode = 1
  })
