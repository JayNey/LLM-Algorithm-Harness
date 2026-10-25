import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSystemLogClient, readLogQuery } from './client.ts'

function clientFor(params: Array<Record<string, unknown>>) {
  const client = createSystemLogClient({
    get: async (_url: string, config?: { params?: unknown }) => {
      params.push((config?.params ?? {}) as Record<string, unknown>)
      // 真实 http 拦截器已解包 ApiResponse.data——这里直接返回内层负载
      return {
        items: [
          {
            id: 2,
            timestamp: 1760000002.5,
            level: 'ERROR',
            message: '任务失败',
            user_id: 'user-1',
            run_id: null,
            context: { route: '/api/v1/evaluations' },
          },
          {
            id: 1,
            timestamp: 1760000001,
            level: 'INFO',
            message: '请求完成',
            user_id: null,
            run_id: 'run-a',
            context: {},
          },
        ],
        total: 2,
        limit: 50,
        offset: 0,
        source: 'retained_api_and_task_events',
      }
    },
  } as never)
  return { client, params }
}

test('日志查询解析（context 原样保留、可空 user/run）', async () => {
  const { client, params } = clientFor([])
  const page = await client.query({ limit: 50, offset: 0, level: 'ERROR' })
  assert.equal(page.total, 2)
  assert.equal(page.items[0].level, 'ERROR')
  assert.equal(page.items[0].user_id, 'user-1')
  assert.equal(page.items[1].run_id, 'run-a')
  assert.deepEqual(page.items[0].context, { route: '/api/v1/evaluations' })
  assert.deepEqual(params[0], { level: 'ERROR', limit: 50, offset: 0 })
})

test('查询参数构造（时间转 epoch 秒、空项省略）', async () => {
  const { client, params } = clientFor([])
  await client.query(
    readLogQuery({
      level: 'warning',
      search: '失败',
      start: '2026-10-24T00:00:00Z',
      end: '',
    }).query,
  )
  assert.deepEqual(params[0], {
    level: 'WARNING',
    search: '失败',
    start: Date.parse('2026-10-24T00:00:00Z') / 1000,
    limit: 50,
    offset: 0,
  })
})

test('输入校验：级别白名单、时间顺序', () => {
  const bad = readLogQuery({
    level: 'VERBOSE',
    search: '',
    start: '2026-10-24T02:00:00Z',
    end: '2026-10-24T01:00:00Z',
  })
  assert.ok(bad.errors.level)
  assert.ok(bad.errors.end)
  const good = readLogQuery({ level: '', search: '', start: '', end: '' })
  assert.deepEqual(good.errors, {})
  assert.deepEqual(good.query, { limit: 50, offset: 0 })
})
