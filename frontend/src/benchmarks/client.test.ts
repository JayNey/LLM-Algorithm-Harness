import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createBenchmarkClient } from './client.ts'

const suiteRow = {
  id: 'suite-1',
  name: '学习曲线套件',
  version: '1.0',
  description: null,
  frozen: false,
  problems: ['p1', 'p2'],
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:00:00Z',
}

function clientFor(
  reply: (config: { method: string; url: string }) => unknown,
) {
  const seen: Array<Record<string, unknown>> = []
  const client = createBenchmarkClient({
    get: async (url: string) => {
      seen.push({ method: 'GET', url })
      return (reply({ method: 'GET', url }) as { data: unknown }).data
    },
    post: async (url: string, body?: unknown) => {
      seen.push({ method: 'POST', url, body })
      return (reply({ method: 'POST', url }) as { data: unknown }).data
    },
    patch: async (url: string, body?: unknown) => {
      seen.push({ method: 'PATCH', url, body })
      return (reply({ method: 'PATCH', url }) as { data: unknown }).data
    },
  } as never)
  return { client, seen }
}

test('suites 全量列表与详情严格解析', async () => {
  const { client, seen } = clientFor(({ url, method }) => {
    if (method === 'GET' && url === '/benchmarks/suites')
      return {
        data: {
          items: [suiteRow],
          total: 1,
          limit: 1,
          offset: 0,
          has_more: false,
        },
      }
    return { data: suiteRow }
  })
  const suites = await client.suites()
  assert.equal(suites.length, 1)
  assert.equal(suites[0].problems.join(','), 'p1,p2')
  assert.equal(suites[0].description, null)
  const detail = await client.getSuite('suite-1')
  assert.equal(detail.version, '1.0')
  assert.equal(seen[0].url, '/benchmarks/suites')
})

test('run 返回 202 数据并携带 task_id；run 详情展示可空指标', async () => {
  const { client } = clientFor(({ method }) => {
    if (method === 'POST')
      return {
        data: {
          ...suiteRow,
          id: 'run-1',
          suite_id: 'suite-1',
          status: 'pending',
          model: null,
          accuracy: null,
          cost_usd: null,
          error_message: null,
          task_id: 'task-b1',
        },
      }
    return {
      data: {
        id: 'run-1',
        suite_id: 'suite-1',
        status: 'completed',
        model: 'model-a',
        accuracy: 0.75,
        cost_usd: 0.03,
        error_message: null,
        created_at: '2026-10-23T00:00:00Z',
        updated_at: '2026-10-23T00:05:00Z',
      },
    }
  })
  const started = await client.runSuite('suite-1', {
    api_key_id: 'k1',
    dataset_path: 'datasets/demo.json',
    model: 'model-a',
  })
  assert.equal(started.task_id, 'task-b1')
  assert.equal(started.status, 'pending')
  const finished = await client.run('run-1')
  assert.equal(finished.accuracy, 0.75)
  assert.equal(finished.model, 'model-a')
})

test('学习曲线解析多模型序列与 trends 可空', async () => {
  const { client } = clientFor(() => ({
    data: {
      suite_id: 'suite-1',
      suite_name: '学习曲线套件',
      data: [
        {
          timestamp: '2026-10-22T00:00:00Z',
          model: 'model-a',
          accuracy: 0.5,
          cost_usd: 0.01,
        },
        {
          timestamp: '2026-10-23T00:00:00Z',
          model: 'model-a',
          accuracy: 0.75,
          cost_usd: 0.03,
        },
        {
          timestamp: '2026-10-23T00:00:00Z',
          model: 'model-b',
          accuracy: null,
          cost_usd: null,
        },
      ],
      trends: { accuracy_growth_rate: 0.5, cost_growth_rate: null },
    },
  }))
  const curve = await client.learningCurve('suite-1')
  assert.equal(curve.data.length, 3)
  assert.equal(curve.data[2].accuracy, null)
  assert.equal(curve.trends.accuracy_growth_rate, 0.5)
  assert.equal(curve.trends.cost_growth_rate, null)
})

test('缺字段或错类型明确拒绝', async () => {
  const { client } = clientFor(() => ({
    data: { id: 'suite-1', name: 'x' }, // 缺 version/frozen/problems 等
  }))
  await assert.rejects(client.getSuite('suite-1'), /基准接口响应格式不兼容/)
})
