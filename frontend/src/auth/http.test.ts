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
