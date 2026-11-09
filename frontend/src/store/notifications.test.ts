import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import {
  bindNotificationRefresh,
  createNotificationGateway,
  createNotificationStore,
  notificationHref,
  notificationInstant,
  notificationPollMs,
  readNotification,
  readNotificationPage,
  type AppNotification,
  type NotificationGateway,
  type NotificationPage,
} from './notifications.ts'

function note(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'note-1',
    kind: 'task_completed',
    titleKey: '任务已完成',
    bodyKey: '已完成 {{completed_count}} / {{total_count}}',
    params: { completed_count: 2, total_count: 4 },
    createdAt: '2026-11-01T06:00:00',
    read: false,
    href: '/evaluations/ev',
    resourceAvailable: true,
    ...overrides,
  }
}

function page(
  items: AppNotification[],
  overrides: Partial<NotificationPage> = {},
): NotificationPage {
  return {
    items,
    nextCursor: null,
    unreadCount: items.filter((item) => !item.read).length,
    serverTime: '2026-11-01T06:00:00',
    ...overrides,
  }
}

function gateway(
  pages: NotificationPage[],
  record: { before: Array<string | null> } = { before: [] },
): NotificationGateway {
  const pending = [...pages]
  return {
    async list() {
      const next = pending.shift()
      if (!next) throw new Error('missing page')
      return next
    },
    async markRead() {},
    async markAll(before) {
      record.before.push(before)
    },
    async clear(before) {
      record.before.push(before)
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('通知从空列表开始，未读数使用接口返回的全量值', async () => {
  const store = createNotificationStore(
    'alice',
    gateway([page([note()], { unreadCount: 8 })]),
  )
  assert.equal(store.getState().notes.length, 0)
  assert.equal(store.getState().unread, 0)
  await store.getState().load()
  assert.equal(store.getState().status, 'ready')
  assert.equal(store.getState().notes.length, 1)
  assert.equal(store.getState().unread, 8)
})

test('空列表、失败后重试和账号切换互不影响', async () => {
  let fail = true
  const first = createNotificationStore('alice', {
    async list() {
      if (fail) throw new Error('unavailable')
      return page([])
    },
    async markRead() {},
    async markAll() {},
    async clear() {},
  })
  await first.getState().load()
  assert.equal(first.getState().status, 'error')
  assert.equal(first.getState().error, '通知暂时无法加载')
  assert.equal(first.getState().notes.length, 0)
  fail = false
  await first.getState().load()
  assert.equal(first.getState().status, 'ready')
  assert.equal(first.getState().notes.length, 0)
  assert.equal(first.getState().unread, 0)

  const loaded = createNotificationStore('alice', gateway([page([note()])]))
  await loaded.getState().load()
  const switched = createNotificationStore('bob', gateway([page([])]))
  assert.equal(switched.getState().notes.length, 0)
  assert.equal(switched.getState().unread, 0)
  assert.equal(loaded.getState().notes.length, 1)
})

test('全部已读和清空使用最近一次服务端时间，过期响应不覆盖新结果', async () => {
  let resolveFirst: (page: NotificationPage) => void = () => {}
  const firstPage = new Promise<NotificationPage>((resolve) => {
    resolveFirst = resolve
  })
  let calls = 0
  const record = { before: [] as Array<string | null> }
  const store = createNotificationStore('alice', {
    async list() {
      calls += 1
      if (calls === 1) return firstPage
      return page([note({ id: 'current', read: true })], { unreadCount: 3 })
    },
    async markRead() {},
    async markAll(before) {
      record.before.push(before)
    },
    async clear(before) {
      record.before.push(before)
    },
  })
  const stale = store.getState().load()
  await store.getState().load()
  resolveFirst(page([note({ id: 'stale' })]))
  await stale
  assert.equal(store.getState().notes[0]?.id, 'current')
  assert.equal(store.getState().unread, 3)
  await store.getState().markAllRead()
  await store.getState().clear()
  assert.deepEqual(record.before, [
    '2026-11-01T06:00:00',
    '2026-11-01T06:00:00',
  ])
})

test('后台刷新沿新游标保留旧尾部，并对账新增和已移除的条目', async () => {
  const items = ['9', '8', '7', '6', '5', '4', '3'].map((id) =>
    note({ id, createdAt: `2026-11-01T06:00:0${id}` }),
  )
  let server = items.slice(2)
  const calls: Array<string | undefined> = []
  const store = createNotificationStore('alice', {
    ...gateway([]),
    async list({ cursor }) {
      calls.push(cursor)
      const start = cursor
        ? server.findIndex((item) => item.id === cursor) + 1
        : 0
      const batch = server.slice(start, start + 2)
      return page(batch, {
        nextCursor:
          start + batch.length < server.length ? batch.at(-1)!.id : null,
        unreadCount: server.length,
      })
    },
  })
  await store.getState().load()
  await store.getState().loadMore()
  assert.deepEqual(
    store.getState().notes.map(({ id }) => id),
    ['7', '6', '5', '4'],
  )

  server = items.filter(({ id }) => id !== '6')
  calls.length = 0
  await store.getState().load()
  assert.deepEqual(calls, [undefined, '8', '5'])
  assert.deepEqual(
    store.getState().notes.map(({ id }) => id),
    ['9', '8', '7', '5', '4', '3'],
  )
  assert.equal(store.getState().nextCursor, null)
  assert.equal(store.getState().unread, 6)
})

for (const action of ['markAllRead', 'clear'] as const) {
  test(`${action} 提交前后的后台刷新不会抢占回读或恢复旧状态`, async () => {
    const old = page([note()])
    const after = action === 'clear' ? page([]) : page([note({ read: true })])
    const writing = deferred<void>()
    const stalePoll = deferred<NotificationPage>()
    const readback = deferred<NotificationPage>()
    const readbackStarted = deferred<void>()
    let calls = 0
    const store = createNotificationStore('alice', {
      ...gateway([]),
      async list() {
        calls += 1
        if (calls === 1) return old
        if (calls === 2) return stalePoll.promise
        if (calls === 3) {
          readbackStarted.resolve()
          return readback.promise
        }
        return old
      },
      markAll: () => writing.promise,
      clear: () => writing.promise,
    })
    await store.getState().load()
    const mutation = store.getState()[action]()
    const earlier = store.getState().load()
    writing.resolve()
    await readbackStarted.promise
    const later = store.getState().load()
    if (action === 'markAllRead') {
      stalePoll.resolve(old)
      await earlier
    }
    readback.resolve(after)
    await mutation
    stalePoll.resolve(old)
    await Promise.all([earlier, later])
    assert.equal(store.getState().unread, 0)
    assert.deepEqual(store.getState().notes, after.items)
  })
}

test('分类切换后只接受当前分类，旧账号的迟到响应与新账号隔离', async () => {
  const stale = deferred<NotificationPage>()
  const oldOwner = deferred<NotificationPage>()
  let calls = 0
  const alice = createNotificationStore('alice', {
    ...gateway([]),
    async list({ kind }) {
      calls += 1
      if (calls === 1) return stale.promise
      if (calls === 3) return oldOwner.promise
      assert.equal(kind, 'system')
      return page([note({ id: 'system', kind })], {
        nextCursor: 'system-cursor',
      })
    },
  })
  const oldFilter = alice.getState().load('budget_alert')
  await alice.getState().load('system')
  stale.resolve(page([note({ id: 'budget', kind: 'budget_alert' })]))
  await oldFilter
  assert.equal(alice.getState().notes[0]?.id, 'system')
  assert.equal(alice.getState().nextCursor, 'system-cursor')

  const oldAccount = alice.getState().load()
  const bob = createNotificationStore('bob', gateway([page([])]))
  await bob.getState().load()
  oldOwner.resolve(page([note({ id: 'alice-only' })]))
  await oldAccount
  assert.deepEqual(bob.getState().notes, [])
  assert.equal(bob.getState().unread, 0)
})

test('切换分类时放弃旧分类的分页请求和加载深度', async () => {
  const stale = deferred<NotificationPage>()
  const store = createNotificationStore('alice', {
    ...gateway([]),
    async list({ kind, cursor }) {
      if (cursor === 'all-cursor') return stale.promise
      if (kind === 'system') {
        assert.equal(cursor, undefined)
        return page([note({ id: 'system', kind })], {
          nextCursor: 'system-cursor',
        })
      }
      return page([note({ id: 'all' })], { nextCursor: 'all-cursor' })
    },
  })
  await store.getState().load()
  const more = store.getState().loadMore()
  await store.getState().load('system')
  stale.resolve(page([note({ id: 'stale' })]))
  await more
  assert.deepEqual(
    store.getState().notes.map(({ id }) => id),
    ['system'],
  )
  assert.equal(store.getState().nextCursor, 'system-cursor')
  assert.equal(store.getState().status, 'ready')
})

test('失效游标从当前分类第一页恢复并继续分页', async () => {
  const calls: Array<string | undefined> = []
  const store = createNotificationStore('alice', {
    ...gateway([]),
    async list({ kind, cursor }) {
      assert.equal(kind, 'system')
      calls.push(cursor)
      if (cursor === 'expired') throw new ApiClientError('invalid cursor', 400)
      if (calls.length === 1) {
        return page([note({ id: 'removed' })], { nextCursor: 'expired' })
      }
      if (!cursor) return page([note({ id: 'head' })], { nextCursor: 'fresh' })
      return page([note({ id: 'tail' })])
    },
  })
  await store.getState().load('system')
  await store.getState().loadMore()
  assert.deepEqual(calls, [undefined, 'expired', undefined, 'fresh'])
  assert.deepEqual(
    store.getState().notes.map(({ id }) => id),
    ['head', 'tail'],
  )
  assert.equal(store.getState().status, 'ready')
})

test('通知时间按 UTC 解释，不可用资源不能导航', () => {
  assert.equal(
    notificationInstant('2026-11-01T06:00:00').toISOString(),
    '2026-11-01T06:00:00.000Z',
  )
  assert.equal(notificationPollMs, 30_000)
  const unavailable = readNotification({
    id: 'gone',
    kind: 'task_completed',
    title_key: '任务已完成',
    body_key: '已完成 {{completed_count}} / {{total_count}}',
    params: { completed_count: 1, total_count: 1 },
    created_at: '2026-11-01T06:00:00',
    read: false,
    href: '/evaluations/missing',
    resource_available: false,
  })
  assert.equal(unavailable.href, null)
  assert.equal(notificationHref(unavailable), null)
  assert.equal(
    notificationHref(note({ href: 'https://example.test/secret' })),
    null,
  )
  assert.equal(notificationHref(note()), '/evaluations/ev')
  assert.throws(() => readNotificationPage({ items: [] }))
})

test('聚焦和轮询会刷新，解除绑定时停止', () => {
  const calls: string[] = []
  let focus: (() => void) | null = null
  let interval: (() => void) | null = null
  let intervalMs = 0
  const stop = bindNotificationRefresh(() => calls.push('refresh'), {
    addEventListener(_type, listener) {
      focus = listener
    },
    removeEventListener() {
      focus = null
    },
    setInterval(handler, ms) {
      interval = handler
      intervalMs = ms
      return 1
    },
    clearInterval() {
      interval = null
    },
  })
  focus?.()
  interval?.()
  assert.equal(intervalMs, 30_000)
  assert.deepEqual(calls, ['refresh', 'refresh'])
  stop()
  assert.equal(focus, null)
  assert.equal(interval, null)
})

test('通知客户端按筛选和游标请求当前用户接口', async () => {
  const urls: string[] = []
  const client = createNotificationGateway({
    async get(url) {
      urls.push(url)
      return {
        items: [
          {
            id: 'note-1',
            kind: 'budget_alert',
            title_key: '预算达到阈值',
            body_key: '已知费用达到预算的 {{threshold_pct}}%',
            params: { threshold_pct: 80 },
            created_at: '2026-11-01T06:00:00',
            read: false,
            href: '/settings/budgets',
            resource_available: true,
          },
        ],
        next_cursor: null,
        unread_count: 4,
        server_time: '2026-11-01T06:00:00',
      }
    },
    async post(url) {
      urls.push(url)
    },
  })
  const loaded = await client.list({
    kind: 'budget_alert',
    cursor: 'cursor/value',
  })
  assert.equal(loaded.unreadCount, 4)
  assert.equal(loaded.items[0]?.href, '/settings/budgets')
  await client.markRead('note/1')
  await client.markAll('2026-11-01T06:00:00')
  await client.clear(null)
  assert.equal(
    urls[0],
    '/notifications?limit=20&cursor=cursor%2Fvalue&kind=budget_alert',
  )
  assert.equal(urls[1], '/notifications/note%2F1/read')
  assert.equal(
    urls[2],
    '/notifications/read-all?before=2026-11-01T06%3A00%3A00',
  )
  assert.equal(urls[3], '/notifications/clear')
})
