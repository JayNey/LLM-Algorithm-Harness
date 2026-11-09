import { createStore } from 'zustand/vanilla'
import { ApiClientError } from '../auth/http.ts'

export const notificationPollMs = 30_000
const loadError = '通知暂时无法加载'

export type NotificationKind = 'task_completed' | 'budget_alert' | 'system'
export type NotificationStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface AppNotification {
  id: string
  kind: NotificationKind
  titleKey: string
  bodyKey: string
  params: Record<string, string | number>
  createdAt: string
  read: boolean
  href: string | null
  resourceAvailable: boolean
}

export interface NotificationPage {
  items: AppNotification[]
  nextCursor: string | null
  unreadCount: number
  serverTime: string
}

export interface NotificationListQuery {
  cursor?: string
  kind?: NotificationKind
}

export interface NotificationGateway {
  list(query: NotificationListQuery): Promise<NotificationPage>
  markRead(id: string): Promise<void>
  markAll(before: string | null): Promise<void>
  clear(before: string | null): Promise<void>
}

export interface NotificationTransport {
  get(url: string): Promise<unknown>
  post(url: string, data?: unknown): Promise<unknown>
}

export interface RefreshEvents {
  addEventListener(type: 'focus', listener: () => void): void
  removeEventListener(type: 'focus', listener: () => void): void
  setInterval(handler: () => void, ms: number): unknown
  clearInterval(id: unknown): void
}

interface NotificationState {
  owner: string
  notes: AppNotification[]
  unread: number
  status: NotificationStatus
  error: string | null
  nextCursor: string | null
  serverTime: string | null
  kind?: NotificationKind
  load: (kind?: NotificationKind | 'all') => Promise<void>
  loadMore: () => Promise<void>
  markRead: (id: string) => Promise<void>
  markAllRead: () => Promise<void>
  clear: () => Promise<void>
}

const kinds = new Set<NotificationKind>([
  'task_completed',
  'budget_alert',
  'system',
])

function protocol(): never {
  throw new ApiClientError('通知响应格式不兼容')
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    protocol()
  }
  return value as Record<string, unknown>
}

function readParams(value: unknown): Record<string, string | number> {
  const data = record(value ?? {})
  const params: Record<string, string | number> = {}
  for (const [key, item] of Object.entries(data)) {
    if (typeof item === 'number' && Number.isFinite(item)) params[key] = item
    else if (typeof item === 'string') params[key] = item
  }
  return params
}

export function notificationInstant(value: string): Date {
  const zoned = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(zoned)
}

export function notificationHref(note: AppNotification): string | null {
  if (!note.resourceAvailable || note.href === null) return null
  if (!note.href.startsWith('/') || note.href.startsWith('//')) return null
  return note.href
}

export function readNotification(value: unknown): AppNotification {
  const data = record(value)
  if (typeof data.id !== 'string' || data.id.length === 0) protocol()
  if (
    typeof data.kind !== 'string' ||
    !kinds.has(data.kind as NotificationKind)
  ) {
    protocol()
  }
  if (typeof data.title_key !== 'string' || typeof data.body_key !== 'string') {
    protocol()
  }
  if (typeof data.created_at !== 'string' || typeof data.read !== 'boolean') {
    protocol()
  }
  if (typeof data.resource_available !== 'boolean') protocol()
  if (data.href !== null && typeof data.href !== 'string') protocol()
  const available = data.resource_available
  if (available && typeof data.href !== 'string') protocol()
  return {
    id: data.id,
    kind: data.kind as NotificationKind,
    titleKey: data.title_key,
    bodyKey: data.body_key,
    params: readParams(data.params),
    createdAt: data.created_at,
    read: data.read,
    href: available ? data.href : null,
    resourceAvailable: available,
  }
}

export function readNotificationPage(value: unknown): NotificationPage {
  const data = record(value)
  if (!Array.isArray(data.items)) protocol()
  if (data.next_cursor !== null && typeof data.next_cursor !== 'string') {
    protocol()
  }
  if (
    typeof data.unread_count !== 'number' ||
    !Number.isSafeInteger(data.unread_count) ||
    data.unread_count < 0
  ) {
    protocol()
  }
  if (typeof data.server_time !== 'string') protocol()
  return {
    items: data.items.map((item) => readNotification(item)),
    nextCursor: data.next_cursor,
    unreadCount: data.unread_count,
    serverTime: data.server_time,
  }
}

function queryString(
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function createNotificationGateway(
  http: NotificationTransport,
): NotificationGateway {
  return {
    async list(query) {
      return readNotificationPage(
        await http.get(
          `/notifications${queryString({
            limit: 20,
            cursor: query.cursor,
            kind: query.kind,
          })}`,
        ),
      )
    },
    async markRead(id) {
      await http.post(`/notifications/${encodeURIComponent(id)}/read`)
    },
    async markAll(before) {
      await http.post(
        `/notifications/read-all${queryString({ before: before ?? undefined })}`,
      )
    },
    async clear(before) {
      await http.post(
        `/notifications/clear${queryString({ before: before ?? undefined })}`,
      )
    },
  }
}

export function bindNotificationRefresh(
  refresh: () => void,
  events: RefreshEvents,
  pollMs = notificationPollMs,
): () => void {
  const onFocus = () => refresh()
  events.addEventListener('focus', onFocus)
  const timer = events.setInterval(() => refresh(), pollMs)
  return () => {
    events.removeEventListener('focus', onFocus)
    events.clearInterval(timer)
  }
}

type NotificationSnapshot = NotificationPage & { depth: number }
type ReadMode = 'refresh' | 'more' | 'mutation'

export function createNotificationStore(
  owner: string,
  gateway: NotificationGateway,
) {
  return createStore<NotificationState>((set, get) => {
    let scopeVersion = 0
    let readVersion = 0
    let pendingRead: ReadMode | null = null
    let depth = 1

    const reportError = () => set({ status: 'error', error: loadError })

    async function read(
      mode: ReadMode,
      request: (
        isCurrent: () => boolean,
      ) => Promise<NotificationSnapshot | undefined>,
    ) {
      const version = ++readVersion
      const isCurrent = () => version === readVersion
      pendingRead = mode
      try {
        const snapshot = await request(isCurrent)
        if (!snapshot || !isCurrent()) return
        depth = snapshot.depth
        set({
          notes: snapshot.items,
          unread: snapshot.unreadCount,
          nextCursor: snapshot.nextCursor,
          serverTime: snapshot.serverTime,
          status: 'ready',
          error: null,
        })
      } catch {
        if (isCurrent()) reportError()
      } finally {
        if (isCurrent()) pendingRead = null
      }
    }

    async function reconcile(
      kind: NotificationKind | undefined,
      targetDepth: number,
      tail: AppNotification | undefined,
      isCurrent: () => boolean,
    ): Promise<NotificationSnapshot | undefined> {
      const items = new Map<string, AppNotification>()
      let cursor: string | undefined
      let serverTime: string | undefined
      for (let pages = 1; isCurrent(); pages += 1) {
        const page = await gateway.list({ kind, cursor })
        if (!isCurrent()) return
        serverTime ??= page.serverTime
        for (const note of page.items) items.set(note.id, note)

        // The API orders canonical UTC timestamps and then IDs, both descending.
        const last = page.items.at(-1)
        const reachedTail =
          !tail ||
          (last &&
            (last.createdAt < tail.createdAt ||
              (last.createdAt === tail.createdAt && last.id <= tail.id)))
        if (!page.nextCursor || (pages >= targetDepth && reachedTail)) {
          return {
            ...page,
            items: [...items.values()],
            serverTime,
            depth: pages,
          }
        }
        cursor = page.nextCursor
      }
    }

    function refresh(mode: 'refresh' | 'mutation') {
      const { kind, notes } = get()
      const targetDepth =
        depth + Number(mode === 'mutation' && pendingRead === 'more')
      return read(mode, (isCurrent) =>
        reconcile(kind, targetDepth, notes.at(-1), isCurrent),
      )
    }

    async function mutate(write: () => Promise<void>) {
      const scope = scopeVersion
      try {
        await write()
      } catch {
        if (scope === scopeVersion) reportError()
        return
      }
      // Start a new snapshot after each successful commit, in the current filter.
      await refresh('mutation')
    }

    return {
      owner,
      notes: [],
      unread: 0,
      status: 'idle',
      error: null,
      nextCursor: null,
      serverTime: null,
      kind: undefined,
      async load(kind) {
        const current = get()
        const nextKind = kind === 'all' ? undefined : (kind ?? current.kind)
        if (nextKind !== current.kind) {
          scopeVersion += 1
          depth = 1
          set({
            kind: nextKind,
            notes: [],
            nextCursor: null,
            error: null,
            status: 'loading',
          })
        } else {
          if (pendingRead === 'mutation' || pendingRead === 'more') return
          if (current.notes.length === 0) {
            set({ status: 'loading', error: null })
          }
        }
        await refresh('refresh')
      },
      async loadMore() {
        const { kind, nextCursor: cursor, notes, serverTime } = get()
        if (!cursor || pendingRead === 'more' || pendingRead === 'mutation')
          return
        const targetDepth = depth + 1
        const refreshing = pendingRead === 'refresh'
        await read('more', async (isCurrent) => {
          if (refreshing) {
            return reconcile(kind, targetDepth, notes.at(-1), isCurrent)
          }
          try {
            const page = await gateway.list({ cursor, kind })
            const items = new Map(notes.map((note) => [note.id, note]))
            for (const note of page.items) items.set(note.id, note)
            return {
              ...page,
              items: [...items.values()],
              serverTime: serverTime ?? page.serverTime,
              depth: targetDepth,
            }
          } catch (error) {
            if (!(
              error instanceof ApiClientError &&
              error.status === 400 &&
              error.message === 'invalid cursor'
            )) {
              throw error
            }
            return reconcile(kind, targetDepth, notes.at(-1), isCurrent)
          }
        })
      },
      markRead: (id) => mutate(() => gateway.markRead(id)),
      markAllRead: () => mutate(() => gateway.markAll(get().serverTime)),
      clear: () => mutate(() => gateway.clear(get().serverTime)),
    }
  })
}
