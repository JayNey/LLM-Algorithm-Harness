import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { ApiClientError, createHttpClient } from '../auth/http.ts'
import {
  clearSession,
  readSession,
  writeSession,
  type StoredSession,
} from '../auth/tokenStore.ts'
import { createAuthStore, type AuthDeps } from './auth.ts'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  }
}

function storages() {
  return { local: memoryStorage(), session: memoryStorage() }
}

const saved: StoredSession = {
  marker: 'saved',
  expiresAt: 10,
  username: 'ada',
}

function tokens(accessToken = 'access') {
  return {
    access_token: accessToken,
    refresh_token: 'refresh',
    expires_in: 30,
  }
}

test('清除后不能恢复会话', () => {
  const box = storages()
  writeSession(true, saved, box)
  clearSession(box)
  assert.equal(readSession(box), null)
})

test('登录写入过期时间并读取当前用户', async () => {
  const box = storages()
  const calls: { method: string; url: string; body?: unknown }[] = []
  const store = createAuthStore()
  await store.getState().login('ada@example.com', 'secret', true, {
    storages: box,
    now: () => 1_000,
    client: {
      async post(url, body) {
        calls.push({ method: 'post', url, body })
        return tokens()
      },
      async get(url) {
        calls.push({ method: 'get', url })
        assert.equal(readSession(box)?.expiresAt, 31_000)
        assert.equal(readSession(box)?.username, null)
        assert.equal(JSON.stringify(readSession(box)).includes('access'), false)
        return { username: 'ada' }
      },
    },
  })

  assert.deepEqual(calls, [
    {
      method: 'post',
      url: '/auth/login',
      body: {
        username: 'ada@example.com',
        password: 'secret',
        remember: true,
      },
    },
    { method: 'get', url: '/users/me' },
  ])
  assert.equal(box.session.length, 0)
  assert.equal(store.getState().session?.expiresAt, 31_000)
  assert.equal(store.getState().session?.username, 'ada')
  assert.equal(
    JSON.stringify(store.getState().session).includes('access'),
    false,
  )
  assert.deepEqual(readSession(box), store.getState().session)
})

test('登录保存响应里的 CSRF 令牌，且不保存访问令牌', async () => {
  const box = storages()
  const store = createAuthStore()
  await store.getState().login('ada', 'secret', true, {
    storages: box,
    now: () => 1_000,
    baseURL: 'http://api.test',
    createClient: (options) =>
      createHttpClient({
        ...options,
        adapter: (config) => {
          if (config.url === '/auth/login') {
            return Promise.resolve({
              config,
              status: 200,
              statusText: 'OK',
              headers: { 'x-csrf-token': 'csrf-1' },
              data: tokens(),
            })
          }
          return Promise.resolve({
            config,
            status: 200,
            statusText: 'OK',
            headers: {},
            data: { username: 'ada' },
          })
        },
      }),
  })
  assert.equal(store.getState().session?.csrfToken, 'csrf-1')
  assert.equal(readSession(box)?.csrfToken, 'csrf-1')
  assert.equal(JSON.stringify(readSession(box)).includes('access'), false)
})

test('不记住我只写入 sessionStorage', async () => {
  const box = storages()
  const store = createAuthStore()
  await store.getState().login('ada', 'secret', false, {
    storages: box,
    now: () => 1_000,
    client: {
      async post() {
        return tokens('tab')
      },
      async get() {
        return { username: 'ada' }
      },
    },
  })
  assert.equal(box.local.length, 0)
  assert.equal(typeof readSession(box)?.marker, 'string')
  assert.equal(JSON.stringify(readSession(box)).includes('tab'), false)
})

test('登录失败不保存会话', async () => {
  const box = storages()
  const store = createAuthStore()
  await assert.rejects(
    () =>
      store.getState().login('ada', 'bad', true, {
        storages: box,
        client: {
          async post() {
            throw new ApiClientError('登录失败', 401)
          },
          async get() {
            throw new Error('不应读取资料')
          },
        },
      }),
    (error: unknown) => error instanceof ApiClientError && error.status === 401,
  )
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('资料失败且不是 401 时保留令牌并留空用户名', async () => {
  const box = storages()
  const store = createAuthStore()
  await store.getState().login('ada@example.com', 'secret', true, {
    storages: box,
    now: () => 1_000,
    client: {
      async post() {
        return tokens()
      },
      async get() {
        throw new ApiClientError('资料不可用', 503)
      },
    },
  })
  assert.equal(store.getState().session?.expiresAt, 31_000)
  assert.equal(store.getState().session?.username, null)
  assert.equal(
    JSON.stringify(store.getState().session).includes('access'),
    false,
  )
  assert.deepEqual(readSession(box), store.getState().session)
})

test('资料请求返回 401 时不保留令牌', async () => {
  const box = storages()
  const store = createAuthStore()
  await assert.rejects(
    () =>
      store.getState().login('ada', 'secret', true, {
        storages: box,
        now: () => 1_000,
        client: {
          async post() {
            return tokens()
          },
          async get() {
            throw new ApiClientError('未授权', 401)
          },
        },
      }),
    (error: unknown) => error instanceof ApiClientError && error.status === 401,
  )
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('退出时撤销会话并清除本地会话', async () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  let logoutUrl = ''
  await store.getState().logout({
    storages: box,
    client: {
      async post(url) {
        logoutUrl = url
      },
      async get() {
        throw new Error('不应读取资料')
      },
    },
  })
  assert.equal(logoutUrl, '/auth/logout')
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('撤销失败仍然清除会话', async () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  await assert.rejects(
    () =>
      store.getState().logout({
        storages: box,
        client: {
          async post() {
            throw new Error('network')
          },
          async get() {
            return undefined
          },
        },
      }),
    /network/,
  )
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('恢复已保存的会话', () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  assert.deepEqual(store.getState().session, saved)
})

test('修改用户名写回记住我的会话', () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  store.getState().updateUsername('grace', { storages: box })
  assert.equal(store.getState().session?.username, 'grace')
  assert.equal(readSession(box)?.username, 'grace')
  assert.equal(readSession(box)?.marker, saved.marker)
  assert.equal(box.local.length, 1)
  assert.equal(box.session.length, 0)
})

test('修改用户名沿用未记住我的会话存储', () => {
  const box = storages()
  writeSession(false, { ...saved, marker: 'tab' }, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  store.getState().updateUsername('grace', { storages: box })
  assert.equal(store.getState().session?.username, 'grace')
  assert.equal(readSession(box)?.username, 'grace')
  assert.equal(readSession(box)?.marker, 'tab')
  assert.equal(box.local.length, 0)
  assert.equal(box.session.length, 1)
})

test('未注入客户端时登录和登出复用同一个实例', async () => {
  const box = storages()
  const store = createAuthStore()
  const deps: AuthDeps = {
    storages: box,
    baseURL: 'http://api.test',
    now: () => 1_000,
  }
  assert.equal(typeof store.getState().httpClient, 'function')
  const client = store.getState().httpClient(deps)
  assert.equal(store.getState().httpClient(deps), client)
  const calls: string[] = []
  client.post = async (url: string) => {
    calls.push(url)
    if (url.endsWith('/auth/login')) return tokens('shared')
    return undefined
  }
  client.get = async (url: string) => {
    calls.push(url)
    return { username: 'ada' }
  }
  await store.getState().login('ada', 'secret', false, deps)
  await store.getState().logout(deps)
  assert.deepEqual(calls, ['/auth/login', '/users/me', '/auth/logout'])
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('登录、当前用户和登出落在配置的 API 根路径上', async () => {
  const baseURL = '/api/v1'
  const box = storages()
  const store = createAuthStore()
  const sent: string[] = []
  const client = {
    async post(url: string) {
      sent.push(url)
      return tokens()
    },
    async get(url: string) {
      sent.push(url)
      return { username: 'ada' }
    },
  }
  await store.getState().login('ada', 'secret', true, {
    storages: box,
    now: () => 1_000,
    baseURL,
    client,
  })
  await store.getState().logout({ storages: box, client })
  assert.deepEqual(
    sent.map((url) => axios.getUri({ baseURL, url })),
    ['/api/v1/auth/login', '/api/v1/users/me', '/api/v1/auth/logout'],
  )
})

test('clear 后不能从存储恢复会话', () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  store.getState().clear({ storages: box })
  assert.equal(readSession(box), null)
  assert.equal(store.getState().session, null)
})

test('从 localStorage 恢复后写入回调仍记住我', async () => {
  const box = storages()
  writeSession(true, saved, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  const placed = await captureRefreshWrite(store, box)
  assert.equal(placed.local, 1)
  assert.equal(placed.session, 0)
  assert.equal(placed.during?.marker, 'next')
})

test('从 sessionStorage 恢复后写入回调不记住我', async () => {
  const box = storages()
  writeSession(false, { ...saved, marker: 'tab' }, box)
  const store = createAuthStore()
  store.getState().hydrate({ storages: box })
  assert.equal(store.getState().session?.marker, 'tab')
  const placed = await captureRefreshWrite(store, box)
  assert.equal(placed.local, 0)
  assert.equal(placed.session, 1)
})

test('刷新写入沿用最近一次登录的记住我', async () => {
  const box = storages()
  const store = createAuthStore()
  let write: ((session: StoredSession) => void) | undefined
  await store.getState().login('ada', 'secret', false, {
    storages: box,
    now: () => 1_000,
    baseURL: 'http://api.test',
    createClient: (options) => {
      write = options.write
      return {
        async post() {
          return tokens('first')
        },
        async get() {
          return { username: 'ada' }
        },
      }
    },
  })
  await store.getState().login('ada@example.com', 'secret', true, {
    storages: box,
    now: () => 1_000,
    baseURL: 'http://api.test',
    createClient: () => ({
      async post() {
        return tokens('second')
      },
      async get() {
        return { username: 'ada' }
      },
    }),
  })
  const refreshWrite = write
  if (refreshWrite === undefined) {
    throw new Error('缺少写入回调')
  }
  refreshWrite({
    marker: 'refreshed',
    expiresAt: 50,
    username: 'ada',
  })
  assert.equal(box.local.length, 1)
  assert.equal(box.session.length, 0)
  assert.equal(readSession(box)?.marker, 'refreshed')
  assert.equal(store.getState().session?.marker, 'refreshed')
})

async function captureRefreshWrite(
  store: ReturnType<typeof createAuthStore>,
  box: ReturnType<typeof storages>,
) {
  let during: StoredSession | null = null
  let local = -1
  let session = -1
  const deps: AuthDeps = {
    storages: box,
    baseURL: 'http://api.test',
    createClient(options) {
      options.write({
        marker: 'next',
        expiresAt: 10,
        username: 'ada',
      })
      during = readSession(box)
      local = box.local.length
      session = box.session.length
      return {
        async post() {
          return undefined
        },
        async get() {
          return undefined
        },
      }
    },
  }
  await store.getState().logout(deps)
  const result: {
    during: StoredSession | null
    local: number
    session: number
  } = { during, local, session }
  return result
}

for (const remember of [false, true]) {
  for (const action of ['clear', 'logout'] as const) {
    test(`刷新晚于${action}返回时不恢复会话，remember=${remember}`, async () => {
      const box = storages()
      const store = createAuthStore()
      let client!: ReturnType<typeof createHttpClient>
      let notifyStarted!: () => void
      const started = new Promise<void>((resolve) => {
        notifyStarted = resolve
      })
      let finish!: (value: ReturnType<typeof tokens>) => void
      const reply = new Promise<ReturnType<typeof tokens>>((resolve) => {
        finish = resolve
      })
      let protectedCalls = 0
      let logoutCalls = 0
      await store.getState().login('ada', 'fake-password', remember, {
        storages: box,
        baseURL: 'http://api.test',
        now: () => 0,
        createClient: (options) => {
          client = createHttpClient({
            ...options,
            adapter: async (config) => {
              let status = 200
              let data: unknown
              if (config.url === '/auth/login') {
                data = { ...tokens(), expires_in: 3600 }
              } else if (config.url === '/users/me') {
                data = { username: 'ada' }
              } else if (config.url === '/auth/refresh') {
                notifyStarted()
                data = await reply
              } else if (config.url === '/auth/logout') {
                logoutCalls += 1
                assert.equal(config.headers.get('Authorization'), undefined)
                assert.equal(config.withCredentials, true)
                status = 204
              } else {
                protectedCalls += 1
                status = protectedCalls === 1 ? 401 : 200
                data = { ok: true }
              }
              return { config, status, statusText: 'test', headers: {}, data }
            },
          })
          return client
        },
      })
      const result = client.get('/slow-protected').then(
        () => false,
        (error: unknown) => {
          assert.ok(error instanceof ApiClientError)
          return true
        },
      )
      await started
      if (action === 'logout') {
        await store.getState().logout({ client, storages: box })
      } else {
        store.getState().clear({ storages: box })
      }
      assert.equal(store.getState().session, null)
      assert.equal(readSession(box), null)
      finish(tokens('late-access'))
      assert.equal(await result, true)
      assert.equal(store.getState().session, null)
      assert.equal(box.local.length, 0)
      assert.equal(box.session.length, 0)
      assert.equal(protectedCalls, 1)
      assert.equal(logoutCalls, action === 'logout' ? 1 : 0)
    })
  }
}
