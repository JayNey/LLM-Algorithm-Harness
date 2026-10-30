import assert from 'node:assert/strict'
import test from 'node:test'
import { reportFilename, createReportClient } from './reports.ts'
import { ApiClientError, createHttpClient } from '../auth/http.ts'

test('权限失败保留状态码，不当成文件成功响应', async () => {
  const http = createHttpClient({
    baseURL: 'https://api.example.test/api/v1',
    now: () => 0,
    read: () => ({ marker: 'owner', expiresAt: 100000, username: 'test' }),
    write: () => {},
    clear: () => {},
    adapter: async (config) => ({
      config,
      status: 403,
      statusText: 'Forbidden',
      headers: {},
      data: new Blob(['denied']),
    }),
  })
  await assert.rejects(
    () => createReportClient(http).download('run', 'html'),
    (error: unknown) => error instanceof ApiClientError && error.status === 403,
  )
})

test('文件响应沿用共享客户端的会话刷新和配置地址', async () => {
  let calls = 0
  let refreshes = 0
  const session = { marker: 'owner', expiresAt: 100000, username: 'test' }
  const http = createHttpClient({
    baseURL: 'https://api.example.test/api/v1',
    now: () => 0,
    read: () => session,
    write: () => {},
    clear: () => {},
    refresh: async () => {
      refreshes++
      return session
    },
    adapter: async (config) => {
      calls++
      assert.equal(config.baseURL, 'https://api.example.test/api/v1')
      assert.equal(config.withCredentials, true)
      return {
        config,
        status: calls === 1 ? 401 : 200,
        statusText: 'test',
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''actual.csv",
        },
        data: new Blob(['a,b']),
      }
    },
  })
  const file = await createReportClient(http).download('run', 'csv')
  assert.equal(calls, 2)
  assert.equal(refreshes, 1)
  assert.equal(file.filename, 'actual.csv')
  assert.equal(await file.blob.text(), 'a,b')
})

test('报告文件名解析 UTF-8 并拒绝路径和控制字符', () => {
  assert.equal(
    reportFilename("attachment; filename*=UTF-8''run%20one.md", 'fallback.md'),
    'run one.md',
  )
  assert.equal(
    reportFilename('attachment; filename="../bad.html"', 'fallback.html'),
    'fallback.html',
  )
  assert.equal(
    reportFilename("attachment; filename*=UTF-8''%00bad.csv", 'fallback.csv'),
    'fallback.csv',
  )
  assert.equal(reportFilename(undefined, 'fallback.csv'), 'fallback.csv')
})

test('报告请求使用编码的运行 ID 和 blob，不绕过注入的认证客户端', async () => {
  let seen: unknown
  const client = createReportClient({
    get: async (
      url: string,
      config: { transformResponse: (body: Blob, headers: unknown) => unknown },
    ) => {
      seen = { url, ...config }
      return config.transformResponse(new Blob(['report']), {
        'content-disposition': "attachment; filename*=UTF-8''report.md",
      })
    },
  } as never)
  const result = await client.download('run one', 'markdown')
  assert.equal((seen as { url: string }).url, '/reports/markdown/run%20one')
  assert.equal((seen as { responseType: string }).responseType, 'blob')
  assert.equal(result.filename, 'report.md')
  assert.equal(await result.blob.text(), 'report')
  await assert.rejects(() => client.download('', 'csv'))
})
