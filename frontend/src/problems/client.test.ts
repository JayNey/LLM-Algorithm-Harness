import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createProblemClient } from './client.ts'
import { readListQuery, writeListQuery } from './validation.ts'

function clientFor(
  reply: (config: { method: string; url: string }) => unknown,
) {
  const seen: Array<Record<string, unknown>> = []
  const client = createProblemClient({
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

test('来源选项与题目列表严格解析（元数据 4 字段）', async () => {
  const { client, seen } = clientFor(({ url }) => {
    if (url === '/evaluation-options')
      return {
        data: {
          strategies: [{ name: 'direct' }],
          sources: [
            { id: 'shared', label: '共享题目', problem_count: 21 },
            { id: 'personal', label: '个人题目', problem_count: 1 },
          ],
        },
      }
    return {
      data: {
        items: [
          {
            problem_id: 'p1',
            title: '两数之和',
            difficulty: 'easy',
            source: 'personal',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      },
    }
  })
  const options = await client.options()
  assert.equal(options.sources[0].problem_count, 21)
  const page = await client.problems({
    source: 'personal',
    limit: 20,
    offset: 0,
  })
  assert.equal(page.items[0].difficulty, 'easy')
  assert.deepEqual(Object.keys(page.items[0]).sort(), [
    'difficulty',
    'problem_id',
    'source',
    'title',
  ])
  assert.equal(seen[1].url, '/evaluation-options/problems')
})

test('列表响应夹带敏感字段也只取元数据；缺字段明确拒绝', async () => {
  const { client } = clientFor(() => ({
    data: {
      items: [
        {
          problem_id: 'p1',
          title: 'x',
          difficulty: null,
          source: 'shared',
          description: 'secret',
          test_cases: [{ expected: 'hidden' }],
          source_url: '/private/path',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
  }))
  const page = await client.problems({ source: 'all', limit: 20, offset: 0 })
  assert.deepEqual(page.items[0], {
    problem_id: 'p1',
    title: 'x',
    difficulty: null,
    source: 'shared',
  })

  const broken = clientFor(() => ({
    data: {
      items: [{ problem_id: 'p1' }],
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    },
  }))
  await assert.rejects(
    broken.client.problems({ source: 'all', limit: 20, offset: 0 }),
    /题目接口响应格式不兼容/,
  )
})

test('同步直导解析完整 validation 报告与错误明细', async () => {
  const { client, seen } = clientFor(({ method }) => {
    if (method === 'POST')
      return {
        data: {
          file_id: 'f1',
          job_id: 'j1',
          validation: {
            total: 5,
            valid: 3,
            invalid: 2,
            errors: [
              { index: 1, error: 'description: missing' },
              { index: 3, error: 'test_cases: wrong type' },
            ],
            errors_truncated: false,
            file_id: 'f1',
            duplicates: 1,
            imported: 3,
            dataset_total: 10,
          },
        },
      }
    return undefined
  })
  const result = await client.directImport(new File(['[]'], 'p.json'), 'append')
  assert.equal(result.validation.imported, 3)
  assert.equal(result.validation.duplicates, 1)
  assert.equal(result.validation.errors[0].index, 1)
  assert.ok(seen[0].body instanceof FormData)
})

test('异步导入链路：上传 → 触发 → 进度含终态报告', async () => {
  const { client, seen } = clientFor(({ method, url }) => {
    if (method === 'POST' && url === '/files/upload')
      return {
        data: { file_id: 'f9', filename: 'p.json', size_bytes: 1024 },
      }
    if (method === 'POST' && url === '/problems/import')
      return { data: { job_id: 'j9', task_id: 't9', status: 'pending' } }
    if (url === '/imports/j9')
      return {
        data: {
          job_id: 'j9',
          status: 'completed',
          processed: 3,
          total: 3,
          percentage: 100,
          result: {
            total: 3,
            valid: 3,
            invalid: 0,
            errors: [],
            errors_truncated: false,
            file_id: 'f9',
            duplicates: 0,
            imported: 3,
            dataset_total: 6,
          },
        },
      }
    return undefined
  })
  const uploaded = await client.uploadFile(new File(['[]'], 'p.json'))
  assert.equal(uploaded.file_id, 'f9')
  const started = await client.startImport('f9', 'append')
  assert.equal(started.task_id, 't9')
  const progress = await client.importJob('j9')
  assert.equal(progress.status, 'completed')
  assert.equal(progress.result?.imported, 3)
  assert.deepEqual(
    seen.map((c) => c.url),
    ['/files/upload', '/problems/import', '/imports/j9'],
  )
})

test('评估历史条目与可空指标解析', async () => {
  const { client } = clientFor(() => ({
    data: {
      items: [
        {
          problem_id: 'p1',
          strategy: 'direct',
          status: 'passed',
          iterations: 2,
          tokens: 120,
          execution_time: 1.5,
          run_id: 'r1',
        },
        {
          problem_id: 'p1',
          strategy: 'reflexion',
          status: 'error',
          iterations: null,
          tokens: null,
          execution_time: null,
          run_id: null,
        },
      ],
      total: 2,
      limit: 20,
      offset: 0,
      has_more: false,
    },
  }))
  const history = await client.problemHistory('p1', { limit: 20, offset: 0 })
  assert.equal(history.items[0].status, 'passed')
  assert.equal(history.items[1].tokens, null)
})

test('URL 来源筛选白名单回填', () => {
  const bogus = readListQuery(new URLSearchParams({ source: 'nope' }))
  assert.equal(bogus.source, 'all')
  const query = readListQuery(new URLSearchParams({ source: 'personal' }))
  const search = writeListQuery(query)
  assert.equal(search.get('source'), 'personal')
  const all = writeListQuery(readListQuery(new URLSearchParams()))
  assert.equal(all.get('source'), null)
})
