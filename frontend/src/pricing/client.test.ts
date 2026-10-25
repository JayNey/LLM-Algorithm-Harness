import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPricingClient, validateOverrideInput } from './client.ts'

function clientFor(
  reply: (config: { method: string; url: string }) => unknown,
) {
  const seen: Array<Record<string, unknown>> = []
  const client = createPricingClient({
    get: async (url: string) => {
      seen.push({ method: 'GET', url })
      return (reply({ method: 'GET', url }) as { data: unknown }).data
    },
    post: async (url: string, body?: unknown) => {
      seen.push({ method: 'POST', url, body })
      return (reply({ method: 'POST', url }) as { data: unknown }).data
    },
  } as never)
  return { client, seen }
}

test('目录解析（三源标注）与历史解析', async () => {
  const { client } = clientFor(({ url }) => {
    if (url === '/pricing')
      return {
        data: {
          models: {
            'model-builtin': {
              prompt_per_1k: 0.5,
              completion_per_1k: 1.5,
              source: 'builtin',
            },
            'model-custom': {
              prompt_per_1k: 0.3,
              completion_per_1k: 0.9,
              source: 'custom_file',
            },
            'model-override': {
              prompt_per_1k: 0.2,
              completion_per_1k: 0.6,
              source: 'override',
            },
          },
        },
      }
    return {
      data: [
        {
          prompt_per_1k: 0.2,
          completion_per_1k: 0.6,
          created_by: 'user-1',
          created_at: '2026-10-24T00:00:00Z',
        },
      ],
    }
  })
  const catalog = await client.catalog()
  assert.equal(catalog.models['model-override']?.source, 'override')
  assert.equal(catalog.models['model-custom']?.prompt_per_1k, 0.3)
  const history = await client.history('model-override')
  assert.equal(history[0].created_by, 'user-1')
})

test('追加自定义定价（POST 语义与校验）', async () => {
  const { client, seen } = clientFor(({ method }) => {
    if (method === 'POST')
      return {
        data: { model: 'model-x', prompt_per_1k: 0.1, completion_per_1k: 0.2 },
      }
    return { data: { models: {} } }
  })
  const result = await client.addOverride({
    modelId: 'model-x',
    prompt_per_1k: 0.1,
    completion_per_1k: 0.2,
  })
  assert.equal(result.model, 'model-x')
  assert.ok(seen[0].url === '/pricing/model-x')
  // 非法输入本地拒绝
  await assert.rejects(
    client.addOverride({
      modelId: '',
      prompt_per_1k: 0,
      completion_per_1k: 0.2,
    }),
    /定价配置无效/,
  )
})

test('目录来源未知明确拒绝', async () => {
  const { client } = clientFor(() => ({
    data: {
      models: {
        bad: { prompt_per_1k: 1, completion_per_1k: 1, source: 'mystery' },
      },
    },
  }))
  await assert.rejects(client.catalog(), /定价接口响应格式不兼容/)
})

test('表单校验（正数价格 + 模型必填）', () => {
  assert.deepEqual(
    validateOverrideInput({
      modelId: ' ',
      prompt_per_1k: '-1',
      completion_per_1k: '0',
    }),
    {
      modelId: '请填写模型 ID',
      prompt_per_1k: '须为正数',
      completion_per_1k: '须为正数',
    },
  )
  assert.deepEqual(
    validateOverrideInput({
      modelId: 'm',
      prompt_per_1k: '0.5',
      completion_per_1k: '1.5',
    }),
    {},
  )
})
