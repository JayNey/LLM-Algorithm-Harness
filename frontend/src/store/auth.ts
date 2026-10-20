import { create } from 'zustand'
import {
  ApiClientError,
  createHttpClient,
  type HttpClientOptions,
} from '../auth/http.ts'
import {
  clearSession,
  readSession,
  writeSession,
  type SessionStorages,
  type StoredSession,
} from '../auth/tokenStore.ts'
import { readViteEnv } from '../config/env.ts'

export interface AuthClient {
  post(url: string, data?: unknown): Promise<unknown>
  get(url: string): Promise<unknown>
  patch(url: string, data?: unknown): Promise<unknown>
  delete(url: string): Promise<unknown>
}

export interface AuthDeps {
  client?: AuthClient
  storages?: SessionStorages
  now?: () => number
  baseURL?: string
  createClient?: (options: HttpClientOptions) => AuthClient
}

interface AuthState {
  session: StoredSession | null
  hydrate: (deps?: AuthDeps) => void
  login: (
    identity: string,
    password: string,
    remember: boolean,
    deps?: AuthDeps,
  ) => Promise<void>
  logout: (deps?: AuthDeps) => Promise<void>
  clear: (deps?: AuthDeps) => void
  updateUsername: (username: string, deps?: AuthDeps) => void
  httpClient: (deps?: AuthDeps) => AuthClient
}

interface LoginPayload {
  expires_in: number
}

function emptyStorage(): Storage {
  return {
    get length() {
      return 0
    },
    clear() {},
    getItem() {
      return null
    },
    key() {
      return null
    },
    removeItem() {},
    setItem() {},
  }
}

function browserStorages(): SessionStorages {
  return { local: localStorage, session: sessionStorage }
}

function loginPayload(value: unknown): LoginPayload {
  if (typeof value !== 'object' || value === null) {
    throw new ApiClientError('服务暂时不可用')
  }
  const record = value as Record<string, unknown>
  if (typeof record.expires_in !== 'number') {
    throw new ApiClientError('服务暂时不可用')
  }
  return { expires_in: record.expires_in }
}

function sessionMarker(): string {
  const cryptoRef = globalThis.crypto
  if (cryptoRef && typeof cryptoRef.randomUUID === 'function') {
    return cryptoRef.randomUUID()
  }
  return `${Date.now()}-${Math.random()}`
}

function profileUsername(value: unknown): string | null {
  if (typeof value !== 'object' || value === null || !('username' in value)) {
    return null
  }
  const username = value.username
  return typeof username === 'string' ? username : null
}

function asAuthClient(client: AuthClient): AuthClient {
  return client
}

export function createAuthStore() {
  let remember = false
  let shared: AuthClient | undefined

  return create<AuthState>((set) => {
    function storagesFrom(deps?: AuthDeps): SessionStorages {
      return deps?.storages ?? browserStorages()
    }

    function clientOptions(
      deps: AuthDeps | undefined,
      box: SessionStorages,
    ): HttpClientOptions {
      return {
        baseURL: deps?.baseURL ?? readViteEnv().apiBaseUrl,
        now: deps?.now ?? Date.now,
        read: () => readSession(box),
        write: (session) => {
          writeSession(remember, session, box)
          set({ session })
        },
        clear: () => {
          clearSession(box)
          set({ session: null })
        },
      }
    }

    function sharedClient(
      deps: AuthDeps | undefined,
      box: SessionStorages,
    ): AuthClient {
      if (!shared) {
        shared = asAuthClient(createHttpClient(clientOptions(deps, box)))
      }
      return shared
    }

    function clientFrom(deps: AuthDeps | undefined, box: SessionStorages) {
      if (deps?.client) return deps.client
      if (deps?.createClient) return deps.createClient(clientOptions(deps, box))
      return sharedClient(deps, box)
    }

    return {
      session: null,
      hydrate(deps) {
        const box = storagesFrom(deps)
        remember =
          readSession({ local: box.local, session: emptyStorage() }) !== null
        set({ session: readSession(box) })
      },
      async login(identity, password, nextRemember, deps) {
        remember = nextRemember
        const box = storagesFrom(deps)
        const client = clientFrom(deps, box)
        const now = deps?.now ?? Date.now
        const payload = loginPayload(
          await client.post('/auth/login', {
            username: identity,
            password,
            remember: nextRemember,
          }),
        )
        const session: StoredSession = {
          marker: sessionMarker(),
          expiresAt: now() + payload.expires_in * 1000,
          username: null,
        }
        writeSession(remember, session, box)
        set({ session })
        try {
          const profile: unknown = await client.get('/users/me')
          const next = { ...session, username: profileUsername(profile) }
          writeSession(remember, next, box)
          set({ session: next })
        } catch (error) {
          if (error instanceof ApiClientError && error.status === 401) {
            clearSession(box)
            set({ session: null })
            throw error
          }
        }
      },
      async logout(deps) {
        const box = storagesFrom(deps)
        try {
          const client = clientFrom(deps, box)
          await client.post('/auth/logout')
        } finally {
          clearSession(box)
          set({ session: null })
        }
      },
      clear(deps) {
        const box = storagesFrom(deps)
        clearSession(box)
        set({ session: null })
      },
      updateUsername(username, deps) {
        const box = storagesFrom(deps)
        const current = readSession(box)
        if (!current) return
        const next = { ...current, username }
        writeSession(remember, next, box)
        set({ session: next })
      },
      httpClient(deps) {
        return sharedClient(deps, storagesFrom(deps))
      },
    }
  })
}

export const useAuthStore = createAuthStore()
