import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { StoredSession } from './tokenStore.ts'
import {
  ApiClientError,
  createHttpClient,
  isAuthEndpoint,
  shouldRefreshBeforeRequest,
  type HttpClientOptions,
} from './http.ts'

function session(overrides: Partial<StoredSession> = {}): StoredSession {
  return {
    accessToken: 'access',
    refreshToken: 'refresh',
    expiresAt: 60_000,
    username: 'ada',
    ...overrides,
  }
}

function envelope(data: unknown) {
  return { success: true, data, message: '' }
}

function resolveWith(
  config: InternalAxiosRequestConfig,
  status: number,
  data: unknown,
  statusText = 'OK',
) {
  return Promise.resolve({
    status,
    statusText,
    headers: {},
    config,
    data,
  })
}

function create(
  overrides: Partial<HttpClientOptions> & Pick<HttpClientOptions, 'adapter'>,
) {
  return createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => session(),
    write: () => undefined,
    clear: () => undefined,
    refresh: async () => {
      throw new Error('不应刷新')
    },
    ...overrides,
  })
}

function headerOf(config: InternalAxiosRequestConfig): string {
  const value = config.headers?.Authorization
  return typeof value === 'string' ? value : ''
}

function bodyOf(data: unknown): unknown {
  if (typeof data === 'string') return JSON.parse(data) as unknown
  return data
}

function retried(config: InternalAxiosRequestConfig): boolean {
  return Boolean((config as { __retried?: boolean }).__retried)
}

function assertApiError(
  error: unknown,
  message: string,
  status: number,
): boolean {
  assert.ok(error instanceof ApiClientError)
  if (!(error instanceof ApiClientError)) return false
  assert.equal(error.message, message)
  assert.equal(error.status, status)
  return true
}

test('受保护请求带 Bearer', async () => {
  const seen: string[] = []
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => ({
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresAt: 60_000,
      username: 'ada',
    }),
    write: () => undefined,
    clear: () => undefined,
    refresh: async () => {
      throw new Error('不应刷新')
    },
    adapter: (config) => {
      seen.push(headerOf(config))
      return Promise.resolve({
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: { success: true, data: { ok: true }, message: '' },
      })
    },
  })
  await client.get('/api/v1/users/me')
  assert.equal(seen[0], 'Bearer access')
})

test('登录请求不刷新', async () => {
  let refreshed = false
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => ({
      accessToken: 'old',
      refreshToken: 'refresh',
      expiresAt: 0,
      username: null,
    }),
    write: () => undefined,
    clear: () => undefined,
    refresh: async () => {
      refreshed = true
      return {
        accessToken: 'new',
        refreshToken: 'next',
        expiresAt: 60_000,
        username: null,
      }
    },
    adapter: (config) =>
      Promise.resolve({
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: { success: true, data: {}, message: '' },
      }),
  })
  await client.post('/api/v1/auth/login', {
    username: 'ada',
    password: 'secret',
  })
  assert.equal(refreshed, false)
})

test('认证端点不刷新且不带 Authorization', async () => {
  const paths = [
    '/api/v1/auth/login',
    '/api/v1/auth/register',
    '/api/v1/auth/refresh',
    '/api/v1/auth/logout',
    '/api/v1/auth/login?next=/dashboard',
  ]
  for (const path of paths) {
    let refreshed = false
    const seen: string[] = []
    const client = create({
      read: () => session({ accessToken: 'old', expiresAt: 0 }),
      refresh: async () => {
        refreshed = true
        return session({ accessToken: 'new' })
      },
      adapter: (config) => {
        seen.push(headerOf(config))
        return resolveWith(config, 200, envelope({}))
      },
    })
    await client.post(path, {})
    assert.equal(refreshed, false, path)
    assert.equal(seen[0], '', path)
  }
})

test('查询里的认证路径不会把普通请求当成认证端点', async () => {
  const seen: string[] = []
  const client = create({
    adapter: (config) => {
      seen.push(headerOf(config))
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  await client.get('/api/v1/users/me?next=/auth/login')
  assert.equal(seen[0], 'Bearer access')
})

test('距过期不足 30 秒时先刷新再用新令牌', async () => {
  const order: string[] = []
  const client = create({
    now: () => 1_000,
    read: () => session({ accessToken: 'old', expiresAt: 1_000 + 29_999 }),
    refresh: async () => {
      order.push('refresh')
      return session({ accessToken: 'new', expiresAt: 90_000 })
    },
    adapter: (config) => {
      order.push(headerOf(config))
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  const result = await client.get('/api/v1/users/me')
  assert.deepEqual(order, ['refresh', 'Bearer new'])
  assert.deepEqual(result, { ok: true })
})

test('过期前刷新后写入新会话', async () => {
  const next = session({
    accessToken: 'new',
    refreshToken: 'next',
    expiresAt: 90_000,
  })
  const written: StoredSession[] = []
  const client = create({
    now: () => 1_000,
    read: () => session({ accessToken: 'old', expiresAt: 1_000 + 29_999 }),
    write: (value) => {
      written.push(value)
    },
    refresh: async () => next,
    adapter: (config) => resolveWith(config, 200, envelope({ ok: true })),
  })
  await client.get('/api/v1/users/me')
  assert.deepEqual(written, [next])
})

test('距过期恰好 30 秒时不刷新', async () => {
  let refreshed = false
  const seen: string[] = []
  const client = create({
    now: () => 1_000,
    read: () => session({ accessToken: 'old', expiresAt: 1_000 + 30_000 }),
    refresh: async () => {
      refreshed = true
      return session({ accessToken: 'new' })
    },
    adapter: (config) => {
      seen.push(headerOf(config))
      return resolveWith(config, 200, envelope({}))
    },
  })
  await client.get('/api/v1/users/me')
  assert.equal(refreshed, false)
  assert.equal(seen[0], 'Bearer old')
})

test('没有会话时不刷新也不带 Authorization', async () => {
  let refreshed = false
  const seen: string[] = []
  const client = create({
    read: () => null,
    refresh: async () => {
      refreshed = true
      return session()
    },
    adapter: (config) => {
      seen.push(headerOf(config))
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  await client.get('/api/v1/users/me')
  assert.equal(refreshed, false)
  assert.equal(seen[0], '')
})

test('成功响应返回 data 字段', async () => {
  const client = create({
    adapter: (config) =>
      resolveWith(
        config,
        200,
        JSON.stringify({ success: true, data: { id: 7 }, message: 'ok' }),
      ),
  })
  const result = await client.get('/api/v1/users/me')
  assert.deepEqual(result, { id: 7 })
})

test('204 返回 undefined 且不解析 JSON', async () => {
  const client = create({
    adapter: (config) => resolveWith(config, 204, 'not-json{', 'No Content'),
  })
  const result = await client.post('/api/v1/auth/logout')
  assert.equal(result, undefined)
})

test('非 2xx 抛出 ApiClientError，消息优先 detail', async () => {
  const client = create({
    adapter: (config) =>
      resolveWith(
        config,
        401,
        { detail: '登录失败', message: '其他' },
        'Unauthorized',
      ),
  })
  await assert.rejects(
    () => client.post('/api/v1/auth/login', {}),
    (error: unknown) => assertApiError(error, '登录失败', 401),
  )
})

test('非 2xx 没有 detail 时使用 message', async () => {
  const client = create({
    adapter: (config) => {
      const response = {
        status: 400,
        statusText: 'Bad Request',
        headers: {},
        config,
        data: { message: '请求无效', details: { username: '必填' } },
      }
      return Promise.reject(
        new AxiosError(
          'Request failed with status code 400',
          AxiosError.ERR_BAD_REQUEST,
          config,
          null,
          response,
        ),
      )
    },
  })
  await assert.rejects(
    () => client.post('/api/v1/auth/register', {}),
    (error: unknown) => assertApiError(error, '请求无效', 400),
  )
})

test('isAuthEndpoint 去掉查询后匹配四条认证路径', () => {
  assert.equal(isAuthEndpoint('/api/v1/auth/login'), true)
  assert.equal(isAuthEndpoint('/api/v1/auth/login?next=/dashboard'), true)
  assert.equal(isAuthEndpoint('/api/v1/auth/register'), true)
  assert.equal(isAuthEndpoint('/api/v1/auth/refresh'), true)
  assert.equal(isAuthEndpoint('/api/v1/auth/logout'), true)
  assert.equal(isAuthEndpoint('/api/v1/users/me'), false)
  assert.equal(isAuthEndpoint('/api/v1/users/me?next=/auth/login'), false)
})

test('shouldRefreshBeforeRequest 在不足 30 秒时为真', () => {
  assert.equal(shouldRefreshBeforeRequest(29_999, 0), true)
  assert.equal(shouldRefreshBeforeRequest(30_000, 0), false)
  assert.equal(shouldRefreshBeforeRequest(0, 1_000), true)
})

test('窗口内的两个请求只刷新一次', async () => {
  let calls = 0
  const client = create({
    now: () => 1_000,
    read: () => session({ accessToken: 'old', expiresAt: 1_000 + 1_000 }),
    refresh: async () => {
      calls += 1
      await new Promise((resolve) => setTimeout(resolve, 20))
      return session({ accessToken: 'new', expiresAt: 90_000 })
    },
    adapter: (config) => {
      assert.equal(headerOf(config), 'Bearer new')
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  const [first, second] = await Promise.all([
    client.get('/api/v1/users/me'),
    client.get('/api/v1/reports'),
  ])
  assert.equal(calls, 1)
  assert.deepEqual(first, { ok: true })
  assert.deepEqual(second, { ok: true })
})

test('两个并发 401 只刷新一次并重试原请求', async () => {
  const now = 5_000
  let current = session({
    accessToken: 'old',
    refreshToken: 'refresh',
    expiresAt: now + 60_000,
    username: 'ada',
  })
  const written: StoredSession[] = []
  const refreshCalls: Array<{ body: unknown; authorization: string }> = []
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => now,
    read: () => current,
    write: (value) => {
      written.push(value)
      current = value
    },
    clear: () => undefined,
    adapter: (config) => {
      const url = config.url ?? ''
      if (url.endsWith('/auth/refresh')) {
        refreshCalls.push({
          body: bodyOf(config.data),
          authorization: headerOf(config),
        })
        return resolveWith(
          config,
          200,
          envelope({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
            token_type: 'bearer',
            expires_in: 30,
          }),
        )
      }
      if (!retried(config)) {
        return resolveWith(config, 401, { detail: '未授权' }, 'Unauthorized')
      }
      assert.equal(headerOf(config), 'Bearer new-access')
      return resolveWith(config, 200, envelope({ path: url }))
    },
  })
  const [first, second] = await Promise.all([
    client.get('/api/v1/users/me'),
    client.get('/api/v1/reports'),
  ])
  assert.equal(refreshCalls.length, 1)
  assert.deepEqual(refreshCalls[0], {
    body: { refresh_token: 'refresh' },
    authorization: '',
  })
  assert.deepEqual(written, [
    {
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
      expiresAt: now + 30 * 1_000,
      username: 'ada',
    },
  ])
  assert.deepEqual(first, { path: '/api/v1/users/me' })
  assert.deepEqual(second, { path: '/api/v1/reports' })
})

test('注入的 refresh 遇到 401 时只调用一次且不发刷新请求', async () => {
  let calls = 0
  const urls: string[] = []
  let current = session({ accessToken: 'old', expiresAt: 60_000 })
  const client = create({
    read: () => current,
    write: (value) => {
      current = value
    },
    refresh: async () => {
      calls += 1
      await new Promise((resolve) => setTimeout(resolve, 20))
      return session({ accessToken: 'new', expiresAt: 90_000 })
    },
    adapter: (config) => {
      urls.push(config.url ?? '')
      if (!retried(config)) {
        return resolveWith(config, 401, { detail: '未授权' }, 'Unauthorized')
      }
      assert.equal(headerOf(config), 'Bearer new')
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  const [first, second] = await Promise.all([
    client.get('/api/v1/users/me'),
    client.get('/api/v1/reports'),
  ])
  assert.equal(calls, 1)
  assert.equal(
    urls.some((url) => url.endsWith('/auth/refresh')),
    false,
  )
  assert.deepEqual(first, { ok: true })
  assert.deepEqual(second, { ok: true })
})

test('刷新请求在执行时读取当前 refresh token', async () => {
  let reads = 0
  const seen: unknown[] = []
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 1_000,
    read: () => {
      reads += 1
      return session({
        accessToken: 'old',
        refreshToken: reads < 2 ? 'early' : 'live',
        expiresAt: 1_000,
        username: 'ada',
      })
    },
    write: () => undefined,
    clear: () => undefined,
    adapter: (config) => {
      const url = config.url ?? ''
      if (url.endsWith('/auth/refresh')) {
        seen.push(bodyOf(config.data))
        return resolveWith(
          config,
          200,
          envelope({
            access_token: 'new',
            refresh_token: 'rotated',
            token_type: 'bearer',
            expires_in: 60,
          }),
        )
      }
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  await client.get('/api/v1/users/me')
  assert.deepEqual(seen, [{ refresh_token: 'live' }])
})

test('窗口内刷新失败时保留服务器的 401 消息', async () => {
  let cleared = 0
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 1_000,
    read: () =>
      session({
        accessToken: 'old',
        refreshToken: 'refresh',
        expiresAt: 1_000 + 1_000,
      }),
    write: () => undefined,
    clear: () => {
      cleared += 1
    },
    adapter: (config) => {
      assert.equal((config.url ?? '').endsWith('/auth/refresh'), true)
      return resolveWith(config, 401, { detail: '刷新已失效' }, 'Unauthorized')
    },
  })
  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) => assertApiError(error, '刷新已失效', 401),
  )
  assert.equal(cleared, 1)
})

test('刷新失败时清除会话并抛出 ApiClientError', async () => {
  let cleared = 0
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => session({ expiresAt: 60_000 }),
    write: () => undefined,
    clear: () => {
      cleared += 1
    },
    adapter: (config) => {
      const url = config.url ?? ''
      if (url.endsWith('/auth/refresh')) {
        return resolveWith(
          config,
          401,
          { detail: '刷新已失效' },
          'Unauthorized',
        )
      }
      return resolveWith(config, 401, { detail: '未授权' }, 'Unauthorized')
    },
  })
  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) => assertApiError(error, '刷新已失效', 401),
  )
  assert.equal(cleared, 1)
})

test('重试仍返回 401 时不再刷新', async () => {
  let refreshCount = 0
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () =>
      session({
        accessToken: 'old',
        refreshToken: 'refresh',
        expiresAt: 60_000,
      }),
    write: () => undefined,
    clear: () => undefined,
    adapter: (config) => {
      const url = config.url ?? ''
      if (url.endsWith('/auth/refresh')) {
        refreshCount += 1
        return resolveWith(
          config,
          200,
          envelope({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
            token_type: 'bearer',
            expires_in: 30,
          }),
        )
      }
      return resolveWith(config, 401, { detail: '仍未授权' }, 'Unauthorized')
    },
  })
  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) => assertApiError(error, '仍未授权', 401),
  )
  assert.equal(refreshCount, 1)
})

test('刷新失败后的下一次请求可以再次刷新', async () => {
  let refreshCount = 0
  let failRefresh = true
  let current = session({
    accessToken: 'old',
    refreshToken: 'refresh',
    expiresAt: 60_000,
  })
  const client = createHttpClient({
    baseURL: 'http://api.test',
    now: () => 0,
    read: () => current,
    write: (value) => {
      current = value
    },
    clear: () => undefined,
    adapter: (config) => {
      const url = config.url ?? ''
      if (url.endsWith('/auth/refresh')) {
        refreshCount += 1
        if (failRefresh) {
          return resolveWith(
            config,
            401,
            { detail: '刷新已失效' },
            'Unauthorized',
          )
        }
        return resolveWith(
          config,
          200,
          envelope({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
            token_type: 'bearer',
            expires_in: 30,
          }),
        )
      }
      if (!retried(config)) {
        return resolveWith(config, 401, { detail: '未授权' }, 'Unauthorized')
      }
      return resolveWith(config, 200, envelope({ ok: true }))
    },
  })
  await assert.rejects(() => client.get('/api/v1/users/me'))
  failRefresh = false
  const result = await client.get('/api/v1/users/me')
  assert.equal(refreshCount, 2)
  assert.deepEqual(result, { ok: true })
})

test('ApiClientError.details 保留响应 details，缺失时为 undefined', async () => {
  const withDetails = create({
    adapter: (config) =>
      Promise.reject(
        new AxiosError(
          'Request failed with status code 400',
          AxiosError.ERR_BAD_REQUEST,
          config,
          null,
          {
            status: 400,
            statusText: 'Bad Request',
            headers: {},
            config,
            data: { message: '请求无效', details: { username: '必填' } },
          },
        ),
      ),
  })
  await assert.rejects(
    () => withDetails.post('/api/v1/auth/register', {}),
    (error: unknown) => {
      assert.ok(error instanceof ApiClientError)
      if (!(error instanceof ApiClientError)) return false
      assert.equal(error.message, '请求无效')
      assert.deepEqual(error.details, { username: '必填' })
      return true
    },
  )

  const withoutDetails = create({
    adapter: (config) =>
      resolveWith(config, 401, { detail: '登录失败' }, 'Unauthorized'),
  })
  await assert.rejects(
    () => withoutDetails.post('/api/v1/auth/login', {}),
    (error: unknown) => {
      assert.ok(error instanceof ApiClientError)
      if (!(error instanceof ApiClientError)) return false
      assert.equal(error.message, '登录失败')
      assert.equal(error.details, undefined)
      return true
    },
  )
})

test('detail 和 message 都缺失时提示服务暂时不可用', async () => {
  const client = create({
    adapter: (config) =>
      Promise.reject(
        new AxiosError(
          'Request failed with status code 500',
          AxiosError.ERR_BAD_RESPONSE,
          config,
          null,
          {
            status: 500,
            statusText: 'Internal Server Error',
            headers: {},
            config,
            data: {},
          },
        ),
      ),
  })
  await assert.rejects(
    () => client.get('/api/v1/users/me'),
    (error: unknown) => assertApiError(error, '服务暂时不可用', 500),
  )
})
