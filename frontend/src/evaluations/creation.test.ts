import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import { createCreationStore } from './creation.ts'
import type {
  CreatePayload,
  Draft,
  Evaluation,
  EvaluationClient,
} from './types.ts'

const draft: Draft = {
  api_key_id: 'key-1',
  model: 'model-1',
  problem_ids: ['p-1', 'p-1'],
  strategy_names: ['direct'],
  budget_cap_usd: '',
}
function evaluation(patch: Partial<Evaluation> = {}): Evaluation {
  return {
    evaluation_id: 'eval-1',
    created_at: '2026-10-21T00:00:00Z',
    updated_at: '2026-10-21T00:00:00Z',
    status: 'pending',
    can_start: true,
    can_cancel: false,
    execution_progress: { completed_units: 0, total_units: 1, percentage: 0 },
    strategy_names: ['direct'],
    model: 'model-1',
    problem_count: 1,
    spent_usd: 0,
    budget_cap_usd: null,
    error_message: null,
    progress: null,
    ...patch,
  }
}
function setup(overrides: Partial<EvaluationClient> = {}) {
  let owner: string | null = 'session-1'
  let path = '/evaluations/new'
  const payloads: CreatePayload[] = [],
    starts: string[] = [],
    reads: string[] = [],
    routed: string[] = []
  const page = { items: [], total: 0, offset: 0, limit: 20, has_more: false }
  const client: EvaluationClient = {
    options: async () => ({ strategies: [], sources: [] }),
    problems: async () => page,
    models: async () => ({
      provider: 'openai',
      models: ['model-1'],
      complete: true,
    }),
    list: async () => page,
    get: async (id) => {
      reads.push(id)
      return evaluation({ evaluation_id: id })
    },
    create: async (payload) => {
      payloads.push(payload)
      return evaluation()
    },
    start: async (id) => {
      starts.push(id)
      return evaluation({ evaluation_id: id, can_start: false })
    },
    cancel: async () => evaluation({ status: 'cancelled', can_start: false }),
    results: async () => page,
    result: async () => ({
      run_id: null,
      status: 'pending',
      created_at: '2026-10-21T00:00:00Z',
      completed_at: null,
      strategies: [],
      problems: page,
    }),
    ...overrides,
  }
  const store = createCreationStore({
    client,
    readOwner: () => owner,
    onCreated: (id) => {
      if (path === '/evaluations/new') routed.push(id)
    },
  })
  store.getState().setDraft(draft)
  return {
    store,
    payloads,
    starts,
    reads,
    routed,
    client,
    setOwner(value: string | null) {
      owner = value
    },
    leave() {
      path = '/results'
    },
  }
}

test('同步双提交共用操作，201保留ID后导航和启动', async () => {
  const pending = Promise.withResolvers<Evaluation>()
  let createCalls = 0
  const h = setup({
    create: () => {
      createCalls++
      return pending.promise
    },
  })
  const phases: string[] = []
  h.store.subscribe((state) => phases.push(state.phase))
  const one = h.store.getState().submit(),
    two = h.store.getState().submit()
  assert.equal(one, two)
  assert.equal(h.store.getState().phase, 'creating')
  pending.resolve(evaluation())
  await Promise.all([one, two])
  assert.equal(createCalls, 1)
  assert.deepEqual(h.starts, ['eval-1'])
  assert.deepEqual(h.routed, ['eval-1'])
  assert.equal(h.store.getState().evaluationId, 'eval-1')
  assert.deepEqual(phases, ['creating', 'created', 'starting', 'queued'])
  await h.store.getState().submit()
  assert.equal(createCalls, 1)
})
test('预算空值省略、零值发送0，数组去重且无Mock字段', async () => {
  for (const [input, expected] of [
    ['', undefined],
    ['0', 0],
  ] as const) {
    const h = setup()
    h.store.getState().setDraft({ budget_cap_usd: input })
    await h.store.getState().submit()
    assert.deepEqual(h.payloads, [
      {
        api_key_id: 'key-1',
        model: 'model-1',
        problem_ids: ['p-1'],
        strategy_names: ['direct'],
        ...(expected === undefined ? {} : { budget_cap_usd: expected }),
      },
    ])
  }
})
test('201后start失败保留ID，重试只GET核对并start', async () => {
  const failure = new ApiClientError('启动响应未知')
  let tries = 0
  const h = setup({
    start: async () => {
      if (++tries === 1) throw failure
      return evaluation({ can_start: false })
    },
  })
  await h.store.getState().submit()
  assert.equal(h.store.getState().phase, 'start-error')
  assert.equal(h.store.getState().evaluationId, 'eval-1')
  assert.equal(h.store.getState().error, failure)
  await h.store.getState().submit()
  assert.equal(tries, 1)
  await h.store.getState().retryStart('eval-1')
  assert.deepEqual(h.reads, ['eval-1'])
  assert.equal(tries, 2)
  assert.equal(h.payloads.length, 1)
  assert.equal(h.store.getState().phase, 'queued')
})
test('创建结果未知禁止重发，用户显式核对reset后才能新建', async () => {
  for (const error of [
    new ApiClientError('超时'),
    new ApiClientError('不可用', 503),
    new ApiClientError('超时', 408),
  ]) {
    let calls = 0
    const h = setup({
      create: async () => {
        calls++
        throw error
      },
    })
    await h.store.getState().submit()
    assert.equal(h.store.getState().phase, 'create-unknown')
    assert.equal(h.store.getState().error, error)
    await h.store.getState().submit()
    await h.store.getState().retryStart('unknown')
    assert.equal(calls, 1)
    assert.deepEqual(h.reads, [])
    assert.deepEqual(h.starts, [])
    h.store.getState().reset('session-1')
    h.store.getState().setDraft(draft)
    await h.store.getState().submit()
    assert.equal(calls, 2)
  }
})
test('明确拒绝与本地无效草稿保留editing', async () => {
  const h = setup({
    create: async () => {
      throw new ApiClientError('配置无效', 422)
    },
  })
  await h.store.getState().submit()
  assert.equal(h.store.getState().phase, 'editing')
  assert.equal(h.store.getState().error?.status, 422)
  const invalid = setup()
  invalid.store.getState().setDraft({ model: '' })
  await invalid.store.getState().submit()
  assert.equal(invalid.store.getState().phase, 'editing')
  assert.ok(invalid.store.getState().error)
  assert.deepEqual(invalid.payloads, [])
})
test('换身份后迟到201不能保存ID、导航或继续start', async () => {
  const pending = Promise.withResolvers<Evaluation>()
  const h = setup({ create: () => pending.promise })
  const task = h.store.getState().submit()
  await Promise.resolve()
  h.setOwner('session-2')
  h.store.getState().reset('session-2')
  pending.resolve(evaluation())
  await task
  assert.equal(h.store.getState().owner, 'session-2')
  assert.equal(h.store.getState().evaluationId, null)
  assert.equal(h.store.getState().phase, 'editing')
  assert.deepEqual(h.starts, [])
  assert.deepEqual(h.routed, [])
})
test('201回调换身份时下一个POST前再次检查owner', async () => {
  let owner = 'session-1'
  const h = setup()
  const store = createCreationStore({
    client: h.client,
    readOwner: () => owner,
    onCreated: () => {
      owner = 'session-2'
    },
  })
  store.getState().setDraft(draft)
  await store.getState().submit()
  assert.equal(store.getState().evaluationId, 'eval-1')
  assert.deepEqual(h.starts, [])
})
test('离页不强制跳回，协调器继续start已确认ID', async () => {
  const pending = Promise.withResolvers<Evaluation>()
  const h = setup({ create: () => pending.promise })
  const task = h.store.getState().submit()
  h.leave()
  pending.resolve(evaluation())
  await task
  assert.deepEqual(h.routed, [])
  assert.deepEqual(h.starts, ['eval-1'])
})
test('旧store迟到模型回调与提交响应不能写新会话', async () => {
  const pending = Promise.withResolvers<Evaluation>()
  const h = setup({ create: () => pending.promise })
  assert.equal(h.store.getState().draft.model, 'model-1')
  const lateSetDraft = h.store.getState().setDraft
  const task = h.store.getState().submit()
  await Promise.resolve()
  h.setOwner('session-2')
  h.store.getState().reset(null)
  lateSetDraft({ model: 'old-model' })
  pending.resolve(evaluation())
  await task
  assert.equal(h.store.getState().draft.model, '')
  assert.equal(h.store.getState().evaluationId, null)
  assert.deepEqual(h.starts, [])
})
test('同owner新操作不被旧成功或失败响应覆盖', async () => {
  for (const rejected of [false, true]) {
    const pending = Promise.withResolvers<Evaluation>()
    let calls = 0
    const h = setup({
      create: () =>
        ++calls === 1
          ? pending.promise
          : Promise.resolve(evaluation({ evaluation_id: 'eval-2' })),
    })
    const oldTask = h.store.getState().submit()
    await Promise.resolve()
    h.store.getState().reset('session-1')
    h.store.getState().setDraft(draft)
    await h.store.getState().submit()
    if (rejected) pending.reject(new ApiClientError('旧失败'))
    else pending.resolve(evaluation())
    await oldTask
    assert.equal(h.store.getState().evaluationId, 'eval-2')
    assert.equal(h.store.getState().phase, 'queued')
    assert.equal(h.store.getState().error, null)
    assert.deepEqual(h.starts, ['eval-2'])
  }
})
test('详情直接重试先GET，can_start=false或GET失败不POST', async () => {
  for (const failure of [false, true]) {
    const h = setup({
      get: async () => {
        if (failure) throw new ApiClientError('无权限', 403)
        return evaluation({ evaluation_id: 'existing', can_start: false })
      },
    })
    await h.store.getState().retryStart('existing')
    assert.deepEqual(h.starts, [])
    assert.deepEqual(h.payloads, [])
    assert.equal(h.store.getState().phase, failure ? 'start-error' : 'queued')
    assert.equal(h.store.getState().evaluationId, 'existing')
  }
})
test('重试GET后换身份不start，迟到start响应不恢复旧会话', async () => {
  for (const stage of ['get', 'start']) {
    const pending = Promise.withResolvers<Evaluation>()
    const h = setup({ [stage]: () => pending.promise })
    const task = h.store.getState().retryStart('existing')
    await Promise.resolve()
    await Promise.resolve()
    h.setOwner(null)
    h.store.getState().reset(null)
    pending.resolve(
      evaluation({ evaluation_id: 'existing', can_start: stage === 'get' }),
    )
    await task
    assert.equal(h.store.getState().owner, null)
    assert.equal(h.store.getState().evaluationId, null)
    assert.equal(h.store.getState().phase, 'editing')
    assert.deepEqual(h.starts, [])
  }
})
test('重试与提交共享锁，认证刷新同marker可继续', async () => {
  const pending = Promise.withResolvers<Evaluation>()
  const h = setup({ get: () => pending.promise })
  const first = h.store.getState().retryStart('existing')
  const second = h.store.getState().retryStart('existing')
  const third = h.store.getState().submit()
  assert.equal(first, second)
  assert.equal(second, third)
  h.setOwner('session-1')
  pending.resolve(evaluation({ evaluation_id: 'existing' }))
  await first
  assert.deepEqual(h.starts, ['existing'])
  assert.deepEqual(h.payloads, [])
})
test('过期owner禁提交重试和改草稿，切密钥立即清空模型', async () => {
  const h = setup()
  assert.equal(h.store.getState().draft.model, 'model-1')
  h.store.getState().setDraft({ api_key_id: 'key-2' })
  assert.equal(h.store.getState().draft.model, '')
  h.setOwner(null)
  h.store.getState().setDraft({ model: 'late-model' })
  await h.store.getState().submit()
  await h.store.getState().retryStart('existing')
  assert.equal(h.store.getState().draft.model, '')
  assert.deepEqual(h.payloads, [])
  assert.deepEqual(h.reads, [])
})

test('provider匿名初始快照复用认证HTTP实例，直接渲染不自动start', async () => {
  const { createServer } = await import('vite')
  const { createElement } = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const { StaticRouter } = await import('react-router-dom')
  const server = await createServer({
    server: { middlewareMode: true, watch: null, hmr: false, ws: false },
    optimizeDeps: { noDiscovery: true, include: [] },
    appType: 'custom',
  })
  try {
    const {
      EvaluationSessionProvider,
      useEvaluationSession,
      createCreatedNavigation,
    } = await server.ssrLoadModule('/src/evaluations/session.tsx')
    const { useAuthStore } = await server.ssrLoadModule('/src/store/auth.ts')
    const urls: string[] = []
    const shared = {
      get: async (url: string) => {
        urls.push(url)
        return evaluation()
      },
    }
    useAuthStore.setState({ session: null, httpClient: () => shared })
    let captured: ReturnType<typeof useEvaluationSession> = null
    function Consumer() {
      captured = useEvaluationSession()
      return createElement('span', null, captured?.owner ?? 'missing')
    }
    const html = renderToStaticMarkup(
      createElement(
        StaticRouter,
        { location: '/evaluations/existing' },
        createElement(EvaluationSessionProvider, null, createElement(Consumer)),
      ),
    )
    assert.match(html, /missing/)
    assert.ok(captured)
    assert.equal(captured.owner, null)
    assert.equal(captured.creationStore.getState().owner, null)
    assert.deepEqual(urls, [])
    await captured.client.get('existing')
    assert.deepEqual(urls, ['/evaluations/existing'])
    // Exercise the real navigation adapter: leave before 201, then return explicitly.
    const navigations: unknown[] = []
    const navigation = createCreatedNavigation(
      '/evaluations/new',
      (...args: unknown[]) => {
        navigations.push(args)
      },
    )
    navigation.update('/results', (...args: unknown[]) => {
      navigations.push(args)
    })
    navigation.onCreated('eval-1')
    assert.deepEqual(navigations, [])
    navigation.update('/evaluations/new', (...args: unknown[]) => {
      navigations.push(args)
    })
    navigation.onCreated('eval/2')
    assert.deepEqual(navigations, [
      ['/evaluations/eval%2F2', { replace: true }],
    ])
  } finally {
    await server.close()
  }
})

test('取消核对能力后调用真实cancel，重复取消与启动共用锁', async () => {
  const response = Promise.withResolvers<Evaluation>()
  const cancels: string[] = []
  const h = setup({
    get: async () => evaluation({ can_cancel: true }),
    cancel: (id) => {
      cancels.push(id)
      return response.promise
    },
  })
  const first = h.store.getState().act('eval-1', 'cancel')
  const second = h.store.getState().act('eval-1', 'cancel')
  const start = h.store.getState().retryStart('eval-1')
  assert.equal(first, second)
  assert.equal(first, start)
  await new Promise((r) => setTimeout(r, 0))
  assert.deepEqual(cancels, ['eval-1'])
  assert.deepEqual(h.starts, [])
  response.resolve(
    evaluation({ status: 'completed', can_start: false, can_cancel: false }),
  )
  await first
  assert.equal(h.store.getState().action?.pending, false)
  assert.equal(h.store.getState().evaluationId, null)
})
test('取消失败保留ID和错误，允许重新核对后重试', async () => {
  let attempts = 0
  const h = setup({
    get: async () => evaluation({ can_cancel: true }),
    cancel: async () => {
      if (++attempts === 1) throw new ApiClientError('取消失败', 503)
      return evaluation({ status: 'cancelled', can_cancel: false })
    },
  })
  await h.store.getState().act('eval-1', 'cancel')
  assert.equal(h.store.getState().action?.pending, false)
  assert.equal(h.store.getState().evaluationId, null)
  assert.equal(h.store.getState().action?.error?.message, '取消失败')
  await h.store.getState().act('eval-1', 'cancel')
  assert.equal(attempts, 2)
  assert.equal(h.store.getState().action?.error, null)
  assert.equal(h.payloads.length, 0)
})
test('终态不允许取消；换owner后迟到GET不发cancel', async () => {
  let cancels = 0
  const get = Promise.withResolvers<Evaluation>()
  const h = setup({
    get: () => get.promise,
    cancel: async () => {
      cancels++
      return evaluation()
    },
  })
  const task = h.store.getState().act('eval-1', 'cancel')
  await Promise.resolve()
  h.setOwner('other-session')
  get.resolve(evaluation({ can_cancel: true }))
  await task
  assert.equal(cancels, 0)
  const terminal = setup({
    cancel: async () => {
      cancels++
      return evaluation()
    },
  })
  await terminal.store.getState().act('eval-1', 'cancel')
  assert.equal(cancels, 0)
  assert.equal(terminal.store.getState().action?.pending, false)
})

test('详情离开或切ID使预检失效，不继续POST且释放共享锁', async () => {
  for (const kind of ['start', 'cancel'] as const) {
    const read = Promise.withResolvers<Evaluation>()
    let posts = 0
    const h = setup({
      get: () => read.promise,
      start: async () => {
        posts++
        return evaluation()
      },
      cancel: async () => {
        posts++
        return evaluation()
      },
    })
    const controller = new AbortController()
    const task = h.store.getState().act('eval-1', kind, controller.signal)
    await Promise.resolve()
    controller.abort()
    read.resolve(evaluation({ can_cancel: true }))
    await task
    assert.equal(posts, 0)
    assert.equal(h.store.getState().action?.pending, false)
    assert.equal(h.store.getState().phase, 'editing')
    assert.equal(h.store.getState().evaluationId, null)
  }
})
test('创建未知时仍可操作已知任务，且不改变未知回执或重新create', async () => {
  let posts = 0
  const h = setup({
    create: async () => {
      throw new ApiClientError('创建超时')
    },
    get: async () => evaluation({ can_cancel: true }),
    cancel: async () => {
      posts++
      return evaluation()
    },
  })
  await h.store.getState().submit()
  assert.equal(h.store.getState().phase, 'create-unknown')
  await h.store.getState().act('known-id', 'cancel')
  assert.equal(posts, 1)
  assert.equal(h.store.getState().phase, 'create-unknown')
  assert.equal(h.store.getState().evaluationId, null)
  await h.store.getState().submit()
  assert.equal(posts, 1)
})
test('现有任务动作保留创建草稿和editing，仍能提交新任务', async () => {
  const h = setup({ get: async () => evaluation({ can_cancel: true }) })
  await h.store.getState().act('existing-id', 'cancel')
  assert.equal(h.store.getState().phase, 'editing')
  assert.equal(h.store.getState().evaluationId, null)
  assert.equal(h.store.getState().draft.model, 'model-1')
  await h.store.getState().submit()
  assert.equal(h.payloads.length, 1)
})
