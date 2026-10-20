const storageKey = 'llm-harness-session'

export interface StoredSession {
  marker: string
  expiresAt: number
  username: string | null
  csrfToken?: string
}

export interface SessionStorages {
  local: Storage
  session: Storage
}

function browserStorages(): SessionStorages {
  return { local: localStorage, session: sessionStorage }
}

function parse(raw: string | null): StoredSession | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as StoredSession & {
      accessToken?: unknown
      refreshToken?: unknown
    }
    if (
      !value.marker ||
      typeof value.expiresAt !== 'number' ||
      value.accessToken !== undefined ||
      value.refreshToken !== undefined
    )
      return null
    const session: StoredSession = {
      marker: value.marker,
      expiresAt: value.expiresAt,
      username: typeof value.username === 'string' ? value.username : null,
    }
    if (typeof value.csrfToken === 'string' && value.csrfToken.length > 0) {
      session.csrfToken = value.csrfToken
    }
    return session
  } catch {
    return null
  }
}

export function writeSession(
  remember: boolean,
  session: StoredSession,
  storages: SessionStorages = browserStorages(),
): void {
  const selected = remember ? storages.local : storages.session
  const other = remember ? storages.session : storages.local
  selected.setItem(storageKey, JSON.stringify(session))
  other.removeItem(storageKey)
}

export function readSession(
  storages: SessionStorages = browserStorages(),
): StoredSession | null {
  return (
    parse(storages.local.getItem(storageKey)) ??
    parse(storages.session.getItem(storageKey))
  )
}

export function clearSession(
  storages: SessionStorages = browserStorages(),
): void {
  storages.local.removeItem(storageKey)
  storages.session.removeItem(storageKey)
}
