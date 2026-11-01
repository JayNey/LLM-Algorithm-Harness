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

export function createNotificationStore(
  owner: string,
  gateway: NotificationGateway,
) {
  let generation = 0
  return createStore<NotificationState>((set, get) => {
    const selectedKind = (kind?: NotificationKind | 'all') =>
      kind === undefined ? get().kind : kind === 'all' ? undefined : kind

    const apply = (page: NotificationPage, notes = page.items) =>
      set({
        notes,
        unread: page.unreadCount,
        nextCursor: page.nextCursor,
        serverTime: page.serverTime,
        status: 'ready',
        error: null,
      })

    const fail = (token: number) => {
      if (token !== generation) return
      set({ status: 'error', error: loadError })
    }

    const replace = async (token: number, kind?: NotificationKind) => {
      const page = await gateway.list({ kind })
      if (token !== generation) return
      apply(page)
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
        const token = ++generation
        const nextKind = selectedKind(kind)
        const switching = nextKind !== get().kind
        set({
          kind: nextKind,
          notes: switching ? [] : get().notes,
          nextCursor: switching ? null : get().nextCursor,
          error: null,
          status:
            switching || get().notes.length === 0 ? 'loading' : get().status,
        })
        try {
          await replace(token, nextKind)
        } catch {
          fail(token)
        }
      },
      async loadMore() {
        const cursor = get().nextCursor
        if (!cursor) return
        const token = ++generation
        try {
          const page = await gateway.list({ cursor, kind: get().kind })
          if (token !== generation) return
          const seen = new Set(get().notes.map((note) => note.id))
          apply(page, [
            ...get().notes,
            ...page.items.filter((note) => !seen.has(note.id)),
          ])
        } catch {
          fail(token)
        }
      },
      async markRead(id) {
        const token = ++generation
        try {
          await gateway.markRead(id)
          await replace(token, get().kind)
        } catch {
          fail(token)
        }
      },
      async markAllRead() {
        const token = ++generation
        try {
          await gateway.markAll(get().serverTime)
          await replace(token, get().kind)
        } catch {
          fail(token)
        }
      },
      async clear() {
        const token = ++generation
        try {
          await gateway.clear(get().serverTime)
          await replace(token, get().kind)
        } catch {
          fail(token)
        }
      },
    }
  })
}
