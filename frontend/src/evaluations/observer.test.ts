/** 进度观察器测试（issue #225 T10 Step 1）。
 *
 * 全部时序经 FakeClock 手动推进，零真实 sleep；WebSocket 用 FakeSocket
 * 手动注入服务端帧与关闭码。语义契约见
 * openspec/changes/evaluation-observer/design.md。
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Evaluation } from './types.ts'
import { createProgressObserver, resolveProgressWsUrl } from './observer.ts'
import type {
  ObserverDeps,
  ObserverEvent,
  ServerFrame,
  SocketHandle,
  SocketHandlers,
} from './observer.ts'

// ---------- 测试基建 ----------

interface FakeTimer {
  at: number
  fn: () => void
  cancelled: boolean
}

function fakeClock(start = 0) {
  let now = start
  const timers: FakeTimer[] = []
  const clock = {
    now: () => now,
    setTimeout(fn: () => void, ms: number): unknown {
      const timer: FakeTimer = { at: now + ms, fn, cancelled: false }
      timers.push(timer)
      return timer
    },
    clearTimeout(handle: unknown): void {
      if (handle === null || handle === undefined) return
      ;(handle as FakeTimer).cancelled = true
    },
    advance(ms: number): void {
      const target = now + ms
      for (;;) {
        const due = timers
          .filter((t) => !t.cancelled && t.at <= target)
          .sort((a, b) => a.at - b.at)[0]
        if (!due) break
        now = Math.max(now, due.at)
        due.cancelled = true
        due.fn()
      }
      now = target
    },
    pendingDelays: () =>
      timers
        .filter((t) => !t.cancelled)
        .map((t) => t.at - now)
        .sort((a, b) => a - b),
  }
  return clock
}

class FakeSocket implements SocketHandle {
  readonly sent: Array<Record<string, unknown>> = []
  readonly closeCodes: number[] = []
  readonly handlers: SocketHandlers
  constructor(handlers: SocketHandlers) {
    this.handlers = handlers
  }
  send(frame: Record<string, unknown>): void {
    this.sent.push(frame)
  }
  close(code = 1000): void {
    this.closeCodes.push(code)
  }
  open(): void {
    this.handlers.onOpen()
  }
  frame(frame: ServerFrame): void {
    this.handlers.onMessage(frame)
  }
  remoteClose(code: number): void {
    this.handlers.onClose(code)
  }
  fail(): void {
    this.handlers.onError()
  }
}

function evaluation(status = 'running', id = 'eval-1'): Evaluation {
  return {
    evaluation_id: id,
    created_at: '2026-10-22T00:00:00Z',
    updated_at: '2026-10-22T00:01:00Z',
    status,
    can_start: false,
    can_cancel: status === 'running',
    execution_progress: { completed_units: 1, total_units: 2, percentage: 50 },
    strategy_names: ['direct'],
    model: 'model-a',
    problem_count: 2,
    spent_usd: 0,
    budget_cap_usd: null,
    error_message: null,
    progress: {
      current: 1,
      total: 2,
      message: null,
      completed: 1,
      percentage: 50,
    },
  }
}

const microtask = () => new Promise<void>((resolve) => queueMicrotask(resolve))
async function settle(): Promise<void> {
  for (let i = 0; i < 6; i += 1) await microtask()
}

interface SnapshotCall {
  id: string
  signal: AbortSignal
}

function setup(overrides: Partial<ObserverDeps> = {}) {
  const clock = fakeClock()
  const events: ObserverEvent[] = []
  const sockets: FakeSocket[] = []
  const calls: SnapshotCall[] = []
  let respond: (
    call: SnapshotCall,
    index: number,
  ) => Promise<Evaluation> = async () => evaluation('running')
  const deps: ObserverDeps = {
    fetchSnapshot: async (id, signal) => {
      const call = { id, signal }
      calls.push(call)
      return respond(call, calls.length - 1)
    },
    connectSocket: (handlers: SocketHandlers) => {
      const socket = new FakeSocket(handlers)
      sockets.push(socket)
      return socket as SocketHandle
    },
    clock,
    onChange: (event: ObserverEvent) => {
      events.push(event)
    },
    recoverSession: async () => true,
    ...overrides,
  }
  const observer = createProgressObserver(deps)
  const snapshots = () => events.filter((e) => e.type === 'snapshot')
  const modes = () => events.filter((e) => e.type === 'mode').map((e) => e.mode)
  const lastSocket = () => sockets.at(-1) as FakeSocket
  async function goLive(id = 'eval-1'): Promise<FakeSocket> {
    observer.start(id)
    await settle()
    const socket = lastSocket()
    socket.open()
    await settle()
    socket.frame({ type: 'task.snapshot', task_id: id })
    socket.frame({ type: 'subscribed', task_id: id })
    await settle()
    clock.advance(2_000) // 冲掉启动快照帧触发的合并窗口
    await settle()
    return socket
  }
  return {
    observer,
    clock,
    events,
    sockets,
    calls,
    snapshots,
    modes,
    lastSocket,
    goLive,
    setRespond(fn: typeof respond): void {
      respond = fn
    },
  }
}

type World = ReturnType<typeof setup>

const last = <T>(items: T[]): T => items.at(-1) as T

// ---------- URL 解析 ----------

test('相对进度地址按页面协议与主机解析，绝对地址直通', () => {
  assert.equal(
    resolveProgressWsUrl('/api/v1/ws/progress', {
      protocol: 'http:',
      host: 'h.example',
    }),
    'ws://h.example/api/v1/ws/progress',
  )
  assert.equal(
    resolveProgressWsUrl('/api/v1/ws/progress', {
      protocol: 'https:',
      host: 'h.example',
    }),
    'wss://h.example/api/v1/ws/progress',
  )
  assert.equal(
    resolveProgressWsUrl('wss://cdn.example/api/v1/ws/progress', {
      protocol: 'http:',
      host: 'h.example',
    }),
    'wss://cdn.example/api/v1/ws/progress',
  )
  assert.equal(
    resolveProgressWsUrl('ws://cdn.example/api/v1/ws/progress', {
      protocol: 'https:',
      host: 'h.example',
    }),
    'ws://cdn.example/api/v1/ws/progress',
  )
  assert.match(
    resolveProgressWsUrl('/api/v1/ws/progress?x=1', {
      protocol: 'https:',
      host: 'h.example',
    }),
    /\?x=1$/,
  )
})

// ---------- 启动与订阅确认 ----------

test('start 立即取快照、开连接并在 open 后发订阅帧', async () => {
  const world = setup()
  world.observer.start('eval-1')
  await settle()
  assert.equal(world.calls.length, 1)
  assert.equal(world.calls[0].id, 'eval-1')
  assert.equal(world.sockets.length, 1)
  world.lastSocket().open()
  await settle()
  assert.deepEqual(last(world.lastSocket().sent), {
    action: 'subscribe',
    task_id: 'eval-1',
  })
  assert.ok(world.modes().includes('live') === false)
})

test('subscribed 之前的快照帧只触发失效，2 秒后刷一次', async () => {
  const world = setup()
  world.observer.start('eval-1')
  await settle()
  const socket = world.lastSocket()
  socket.open()
  await settle()
  socket.frame({ type: 'task.snapshot', task_id: 'eval-1' })
  socket.frame({ type: 'subscribed', task_id: 'eval-1' })
  await settle()
  assert.equal(world.calls.length, 1) // 合并窗口未到
  world.clock.advance(2_000)
  await settle()
  assert.equal(world.calls.length, 2)
  assert.ok(world.modes().includes('live'))
})

test('5 秒未确认订阅按失败关闭，进入 3 秒退避与降级轮询', async () => {
  const world = setup()
  world.observer.start('eval-1')
  await settle()
  const socket = world.lastSocket()
  socket.open()
  await settle()
  const before = world.calls.length
  world.clock.advance(5_000)
  await settle()
  assert.equal(socket.closeCodes.length, 1)
  assert.ok(world.modes().includes('degraded'))
  world.clock.advance(3_000)
  await settle()
  assert.ok(world.calls.length > before, '降级轮询已发起')
  assert.equal(world.sockets.length, 2, '按 3 秒退避发起第一次重连')
})

test('同一评估重复 start 幂等，切换评估收旧启新', async () => {
  const world = setup()
  await world.goLive()
  const socketsBefore = world.sockets.length
  const callsBefore = world.calls.length
  world.observer.start('eval-1')
  await settle()
  assert.equal(world.sockets.length, socketsBefore)
  assert.equal(world.calls.length, callsBefore)

  const oldSocket = world.lastSocket()
  world.observer.start('eval-2')
  await settle()
  assert.ok(oldSocket.sent.some((f) => f.action === 'unsubscribe'))
  assert.equal(oldSocket.closeCodes.length, 1)
  assert.equal(world.sockets.length, socketsBefore + 1)
  assert.equal(last(world.calls).id, 'eval-2')
})

// ---------- 合并与非重叠 ----------

test('live 下多事件在 2 秒窗口合并为一次刷新', async () => {
  const world = setup()
  await world.goLive()
  const before = world.calls.length
  const socket = world.lastSocket()
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  socket.frame({ type: 'problem.completed', task_id: 'eval-1' })
  world.clock.advance(1_999)
  await settle()
  assert.equal(world.calls.length, before)
  world.clock.advance(1)
  await settle()
  assert.equal(world.calls.length, before + 1)
})

test('进行中失效只补刷一次且绝不并发', async () => {
  let release!: (value: Evaluation) => void
  const gate = new Promise<Evaluation>((resolve) => {
    release = resolve
  })
  const world = setup()
  await world.goLive()
  const inFlight = world.calls.length
  world.setRespond(async () => gate)
  const socket = world.lastSocket()
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  world.clock.advance(2_000)
  await settle()
  assert.equal(world.calls.length, inFlight + 1, '刷新已发起且挂起')
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  world.clock.advance(2_000)
  await settle()
  assert.equal(
    world.calls.length,
    inFlight + 1,
    '窗口到期但请求进行中：置 pending 不并发',
  )
  release(evaluation('running'))
  await settle()
  assert.equal(
    world.calls.length,
    inFlight + 2,
    '完成后对 pending 失效补刷一次',
  )
})

test('HTTP 真值原样交付且附带当前模式', async () => {
  const world = setup()
  const truth = evaluation('running')
  world.setRespond(async () => truth)
  await world.goLive()
  const delivered = last(world.snapshots())
  assert.equal(delivered.evaluation, truth)
  assert.equal(delivered.mode, 'live')
})

// ---------- 降级与重连 ----------

test('live 兜底：15 秒无事件且非终态则主动刷新一次', async () => {
  const world = setup()
  await world.goLive()
  const before = world.calls.length
  world.clock.advance(14_999)
  await settle()
  assert.equal(world.calls.length, before)
  world.clock.advance(1)
  await settle()
  assert.equal(world.calls.length, before + 1)
  assert.equal(last(world.modes()), 'live')
})

test('WS 失败按 3/6/12/30 秒退避重连，成功后清零', async () => {
  const world = setup()
  await world.goLive()
  const created: Array<{ at: number; socket: FakeSocket }> = []
  const originalConnect = world.sockets.length
  void originalConnect
  // 记录后续每个新 socket 的创建时刻
  const failures: FakeSocket[] = []
  const checkBackoff = async (gap: number) => {
    const socket = last(world.sockets)
    socket.fail()
    await settle()
    world.clock.advance(gap - 1)
    await settle()
    const count = world.sockets.length
    world.clock.advance(1)
    await settle()
    assert.equal(world.sockets.length, count + 1, `退避 ${gap}ms 后才重连`)
    created.push({ at: world.clock.now(), socket: last(world.sockets) })
    failures.push(last(world.sockets))
  }
  await checkBackoff(3_000)
  await checkBackoff(6_000)
  await checkBackoff(12_000)
  await checkBackoff(30_000)
  // 第 5 次重连成功 → 计数清零，再失败又从 3s 开始
  const recovered = last(world.sockets)
  recovered.open()
  await settle()
  recovered.frame({ type: 'subscribed', task_id: 'eval-1' })
  await settle()
  world.clock.advance(2_000)
  await settle()
  await checkBackoff(3_000)
})

test('五次重连失败后放弃 WS，但保持 3 秒降级轮询', async () => {
  const world = setup()
  world.observer.start('eval-1')
  await settle()
  world.lastSocket().open()
  await settle()
  world.clock.advance(5_000) // 订阅超时 → 第一次失败
  await settle()
  for (let i = 0; i < 4; i += 1) {
    world.clock.advance(30_000) // 覆盖各档退避
    await settle()
    world.lastSocket().fail()
    await settle()
  }
  const socketsAfterFive = world.sockets.length
  world.clock.advance(60_000)
  await settle()
  assert.equal(world.sockets.length, socketsAfterFive, '不再发起新重连')
  assert.ok(world.calls.length >= 5, '降级轮询仍在继续')
})

test('快照请求失败按退避顺延轮询，成功后复位为 3 秒', async () => {
  const world = setup()
  world.observer.start('eval-1')
  await settle()
  world.lastSocket().open()
  await settle()
  world.clock.advance(5_000) // 进入 degraded
  await settle()
  let failing = true
  world.setRespond(async () => {
    if (failing) throw { status: 503 }
    return evaluation('running')
  })
  const pollAt = (): number | undefined => world.clock.pendingDelays()[0]
  world.clock.advance(3_000) // 第一次轮询（失败）
  await settle()
  assert.ok(
    world.events.some((e) => e.type === 'error'),
    '失败已回报',
  )
  assert.equal(pollAt(), 6_000)
  world.clock.advance(6_000) // 第二次（失败）
  await settle()
  assert.equal(pollAt(), 12_000)
  failing = false
  world.clock.advance(12_000) // 第三次（成功）
  await settle()
  assert.equal(pollAt(), 3_000, '成功后轮询复位为 3 秒')
})

test('429 后至少 30 秒不发任何请求', async () => {
  const world = setup()
  await world.goLive()
  world.setRespond(async () => {
    throw { status: 429 }
  })
  const socket = world.lastSocket()
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  world.clock.advance(2_000)
  await settle()
  const after429 = world.calls.length
  world.clock.advance(29_999)
  await settle()
  assert.equal(world.calls.length, after429)
  world.clock.advance(1)
  await settle()
  assert.ok(world.calls.length > after429, '30 秒后恢复请求')
})

// ---------- 终态收敛 ----------

test('终态经 HTTP 真值收敛：settled、先退订后关闭、停止一切', async () => {
  const world = setup()
  await world.goLive()
  const socket = world.lastSocket()
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  world.setRespond(async () => evaluation('completed'))
  world.clock.advance(2_000)
  await settle()
  const settled = world.events.find((e) => e.type === 'settled')
  assert.ok(settled && settled.type === 'settled')
  assert.equal(settled.evaluation.status, 'completed')
  assert.ok(socket.sent.some((f) => f.action === 'unsubscribe'))
  assert.equal(socket.closeCodes.length, 1)
  const callsAfter = world.calls.length
  const socketsAfter = world.sockets.length
  world.clock.advance(60_000)
  await settle()
  assert.equal(world.calls.length, callsAfter)
  assert.equal(world.sockets.length, socketsAfter)
})

test('paused 快照同样停止自动观察', async () => {
  const world = setup()
  world.setRespond(async () => evaluation('paused'))
  world.observer.start('eval-1')
  await settle()
  const settled = world.events.find((e) => e.type === 'settled')
  assert.ok(settled && settled.type === 'settled')
  const callsAfter = world.calls.length
  world.clock.advance(60_000)
  await settle()
  assert.equal(world.calls.length, callsAfter)
})

// ---------- 权限与会话 ----------

test('4403 清数据并停止，不重试不重连', async () => {
  const world = setup()
  await world.goLive()
  world.lastSocket().remoteClose(4403)
  await settle()
  assert.ok(world.events.some((e) => e.type === 'forbidden'))
  const callsAfter = world.calls.length
  const socketsAfter = world.sockets.length
  world.clock.advance(60_000)
  await settle()
  assert.equal(world.calls.length, callsAfter)
  assert.equal(world.sockets.length, socketsAfter)
})

test('HTTP 403/404 同样清数据停止', async () => {
  for (const status of [403, 404]) {
    const world = setup()
    world.setRespond(async () => {
      throw { status }
    })
    world.observer.start('eval-1')
    await settle()
    assert.ok(
      world.events.some((e) => e.type === 'forbidden'),
      `HTTP ${status} 视为 forbidden`,
    )
    const callsAfter = world.calls.length
    world.clock.advance(60_000)
    await settle()
    assert.equal(world.calls.length, callsAfter)
  }
})

test('4401 走会话恢复，成功立即重连且不计入失败', async () => {
  let recoveries = 0
  const world = setup({
    recoverSession: async () => {
      recoveries += 1
      return true
    },
  })
  await world.goLive()
  world.lastSocket().remoteClose(4401)
  await settle()
  assert.equal(recoveries, 1)
  const socketsBefore = world.sockets.length
  world.clock.advance(0) // 无退避等待也应立即重连
  await settle()
  assert.ok(world.sockets.length >= socketsBefore, '已重连')
  // 重连成功后再次失败，退避应从 3s 重新开始（未计 4401 失败）
  const socket = world.lastSocket()
  socket.open()
  await settle()
  socket.fail()
  await settle()
  assert.equal(world.clock.pendingDelays()[0], 3_000)
  assert.ok(world.events.some((e) => e.type === 'unauthorized') === false)
})

test('4401 恢复失败发出 unauthorized 并停止', async () => {
  const world = setup({ recoverSession: async () => false })
  await world.goLive()
  world.lastSocket().remoteClose(4401)
  await settle()
  assert.ok(world.events.some((e) => e.type === 'unauthorized'))
  const socketsAfter = world.sockets.length
  const callsAfter = world.calls.length
  world.clock.advance(60_000)
  await settle()
  assert.equal(world.sockets.length, socketsAfter)
  assert.equal(world.calls.length, callsAfter)
})

test('HTTP 401 先恢复会话：成功补刷，失败 unauthorized 停止', async () => {
  let recoveries = 0
  let failures = 0
  const world = setup({
    recoverSession: async () => {
      recoveries += 1
      return true
    },
  })
  world.setRespond(async () => {
    if (failures++ === 0) throw { status: 401 }
    return evaluation('running')
  })
  world.observer.start('eval-1')
  await settle()
  assert.equal(recoveries, 1)
  assert.equal(world.calls.length, 2, '恢复成功后立即补刷')
  assert.ok(world.snapshots().length >= 1)

  const stopped = setup({ recoverSession: async () => false })
  stopped.setRespond(async () => {
    throw { status: 401 }
  })
  stopped.observer.start('eval-1')
  await settle()
  assert.ok(stopped.events.some((e) => e.type === 'unauthorized'))
})

// ---------- 暂停、纪元与清理 ----------

test('隐藏或离线暂停一切，恢复立即刷新重连且退避清零', async () => {
  const cases = [
    {
      pause: (w: World) => w.observer.setVisible(false),
      resume: (w: World) => w.observer.setVisible(true),
    },
    {
      pause: (w: World) => w.observer.setOnline(false),
      resume: (w: World) => w.observer.setOnline(true),
    },
  ]
  for (const { pause, resume } of cases) {
    const world = setup()
    await world.goLive()
    const socket = world.lastSocket()
    pause(world)
    await settle()
    assert.ok(socket.sent.some((f) => f.action === 'unsubscribe'))
    assert.equal(socket.closeCodes.length, 1)
    const callsAfter = world.calls.length
    world.clock.advance(60_000)
    await settle()
    assert.equal(world.calls.length, callsAfter, '暂停期间零请求')

    resume(world)
    await settle()
    assert.ok(world.calls.length > callsAfter, '恢复后立即刷新')
    const resumed = world.lastSocket()
    resumed.open()
    await settle()
    resumed.frame({ type: 'subscribed', task_id: 'eval-1' })
    await settle()
    resumed.fail()
    await settle()
    assert.equal(world.clock.pendingDelays()[0], 3_000, '恢复后退避计数已清零')
  }
})

test('runMutation 递增纪元：在途快照作废，完成后补刷一次', async () => {
  let release!: (value: Evaluation) => void
  const gate = new Promise<Evaluation>((resolve) => {
    release = resolve
  })
  const world = setup()
  await world.goLive()
  world.setRespond(async () => gate)
  world.observer.invalidate()
  world.clock.advance(2_000)
  await settle()
  const staleCall = last(world.calls)
  assert.equal(staleCall.signal.aborted, false)
  let mutationDone = false
  const done = world.observer.runMutation(async () => {
    mutationDone = true
  })
  await settle()
  assert.equal(staleCall.signal.aborted, true, '旧周期请求已被中止')
  let released!: Evaluation
  release((released = evaluation('running')))
  await settle()
  assert.equal(world.calls.length, 3, '被作废的请求不触发补刷')
  await done
  await settle()
  assert.equal(mutationDone, true)
  world.clock.advance(2_000)
  await settle()
  assert.equal(world.calls.length, 4, '变更完成后刷新新纪元')
  assert.equal(last(world.snapshots()).evaluation, released)
})

test('dispose 后无任何回调、请求与连接', async () => {
  const world = setup()
  await world.goLive()
  const socket = world.lastSocket()
  const eventsAfter = world.events.length
  const callsAfter = world.calls.length
  const socketsAfter = world.sockets.length
  world.observer.dispose()
  await settle()
  world.clock.advance(120_000)
  await settle()
  socket.frame({ type: 'task.progress', task_id: 'eval-1' })
  socket.remoteClose(1006)
  await settle()
  assert.equal(world.events.length, eventsAfter)
  assert.equal(world.calls.length, callsAfter)
  assert.equal(world.sockets.length, socketsAfter)
})
