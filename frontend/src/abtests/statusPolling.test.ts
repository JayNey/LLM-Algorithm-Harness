import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import type { ABTestJob } from './types.ts'
import { createStatusPollingSession, STATUS_POLL_MS } from './statusPolling.ts'

const job = (overrides: Partial<ABTestJob> = {}): ABTestJob => ({
  id: 'ab-1',
  name: '提示词对比',
  status: 'running',
  config: {
    name: '提示词对比',
    dataset_path: 'datasets/demo.json',
    model: { model: 'model-a', temperature: 0.7 },
    strategy: { name: 'vanilla' },
    prompt_variants: [{ id: 'baseline' }, { id: 'treatment' }],
    seed: 42,
    max_workers: 4,
    api_key_id: 'k1',
  },
  error_message: null,
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:05:00Z',
  ...overrides,
})

interface ScheduledEntry {
  cb: () => void
  ms: number
  cancelled: boolean
  cancel: () => void
}

function setup(queue: Array<() => Promise<ABTestJob>>) {
  const updates: Array<{
    job: ABTestJob | null
    paused: boolean
    error: string | null
    fatal: boolean
  }> = []
  const scheduled: ScheduledEntry[] = []
  const signals: Array<AbortSignal | undefined> = []
  let calls = 0
  const client = {
    get: async (_testId: string, signal?: AbortSignal) => {
      calls += 1
      signals.push(signal)
      const step = queue[Math.min(calls - 1, queue.length - 1)]
      return step()
    },
  }
  const schedule = (cb: () => void, ms: number) => {
    const entry: ScheduledEntry = {
      cb,
      ms,
      cancelled: false,
      cancel: () => {
        entry.cancelled = true
      },
    }
    scheduled.push(entry)
    return entry.cancel
  }
  const session = createStatusPollingSession({
    client,
    testId: 'ab-1',
    schedule,
    onUpdate: (snapshot) => updates.push({ ...snapshot }),
  })
  return {
    session,
    updates,
    scheduled,
    calls: () => calls,
    signals: () => signals,
    async runNext(): Promise<void> {
      const entry = scheduled.at(-1)
      assert.ok(entry, 'expected a scheduled follow-up tick')
      entry.cb()
      await session.tick()
    },
  }
}

test('运行中成功：记录快照并按固定间隔安排下一轮', async () => {
  const h = setup([() => Promise.resolve(job())])
  await h.session.tick()
  assert.deepEqual(h.updates[0], {
    job: job(),
    paused: false,
    error: null,
    fatal: false,
  })
  assert.equal(h.scheduled.length, 1)
  assert.equal(h.scheduled[0].ms, STATUS_POLL_MS)
})

test('终态完成：暂停且不再安排下一轮', async () => {
  const h = setup([() => Promise.resolve(job({ status: 'completed' }))])
  await h.session.tick()
  assert.equal(h.updates[0].paused, true)
  assert.equal(h.updates[0].fatal, false)
  assert.equal(h.updates[0].error, null)
  assert.equal(h.scheduled.length, 0)
})

test('终态失败：轮询暂停，业务错误由快照的 error_message 呈现', async () => {
  const h = setup([
    () =>
      Promise.resolve(
        job({ status: 'failed', error_message: '执行器返回非法输出' }),
      ),
  ])
  await h.session.tick()
  assert.equal(h.updates[0].paused, true)
  assert.equal(h.updates[0].error, null)
  assert.equal(h.updates[0].job?.error_message, '执行器返回非法输出')
  assert.equal(h.scheduled.length, 0)
})

test('5xx 暂时性故障：错误可见、旧快照保留且继续轮询，恢复后清零', async () => {
  const h = setup([
    () => Promise.reject(new ApiClientError('服务暂时不可用', 500)),
    () => Promise.resolve(job({ status: 'completed' })),
  ])
  await h.session.tick()
  assert.equal(h.updates[0].error, '服务暂时不可用')
  assert.equal(h.updates[0].fatal, false)
  assert.equal(h.updates[0].paused, false)
  assert.equal(h.scheduled.length, 1)
  await h.runNext()
  assert.equal(h.updates[1].error, null)
  assert.equal(h.updates[1].job?.status, 'completed')
  assert.equal(h.updates[1].paused, true)
})

test('断网（非 ApiClientError）同样视为暂时性故障', async () => {
  const h = setup([() => Promise.reject(new TypeError('Failed to fetch'))])
  await h.session.tick()
  assert.equal(h.updates[0].error, 'Failed to fetch')
  assert.equal(h.updates[0].fatal, false)
  assert.equal(h.scheduled.length, 1)
})

test('403：权限终止，停止轮询且后续 tick 不再请求', async () => {
  const h = setup([
    () => Promise.reject(new ApiClientError('没有权限访问', 403)),
  ])
  await h.session.tick()
  assert.equal(h.updates[0].fatal, true)
  assert.equal(h.updates[0].paused, true)
  assert.equal(h.updates[0].error, '没有权限访问')
  assert.equal(h.scheduled.length, 0)
  await h.session.tick()
  assert.equal(h.calls(), 1)
})

test('404：资源终止，停止轮询', async () => {
  const h = setup([() => Promise.reject(new ApiClientError('测试不存在', 404))])
  await h.session.tick()
  assert.equal(h.updates[0].fatal, true)
  assert.equal(h.updates[0].paused, true)
  assert.equal(h.scheduled.length, 0)
})

test('成功后出错：旧快照保留；再成功后错误清零', async () => {
  const h = setup([
    () => Promise.resolve(job()),
    () => Promise.reject(new ApiClientError('网关超时', 504)),
    () => Promise.resolve(job({ status: 'completed' })),
  ])
  await h.session.tick()
  assert.equal(h.updates[0].job?.status, 'running')
  await h.runNext()
  assert.equal(h.updates[1].error, '网关超时')
  assert.equal(h.updates[1].job?.status, 'running')
  await h.runNext()
  assert.equal(h.updates[2].error, null)
  assert.equal(h.updates[2].job?.status, 'completed')
})

test('dispose：在途请求中止、不再更新且取消已排定的下一轮', async () => {
  let resolveInFlight: ((value: ABTestJob) => void) | null = null
  const h = setup([
    () =>
      new Promise<ABTestJob>((resolve) => {
        resolveInFlight = resolve
      }),
    () => Promise.resolve(job()),
  ])
  const pending = h.session.tick()
  h.session.dispose()
  assert.equal(h.signals().at(-1)?.aborted, true)
  resolveInFlight?.(job())
  await pending
  assert.equal(h.updates.length, 0)
  assert.equal(h.scheduled.length, 0)
})
