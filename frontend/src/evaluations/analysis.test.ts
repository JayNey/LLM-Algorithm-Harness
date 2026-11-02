import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { createServer } from 'vite'

// Compile the real TSX with the app's Vite configuration; effects do not run
// on the server, so this covers scope labelling, structure and the no-fetch
// guarantee, while data loading is exercised by the browser fixture.
const server = await createServer({
  server: { middlewareMode: true, watch: null, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true, include: [] },
  appType: 'custom',
})
after(() => server.close())
const {
  AnalysisSection,
  AnalysisUnavailable,
  normalizeFilters,
  tokenChartView,
} = await server.ssrLoadModule('/src/evaluations/analysis.tsx')
const { useAuthStore } = await server.ssrLoadModule('/src/store/auth.ts')
const requests: string[] = []
async function unexpectedRequest(url: string) {
  requests.push(url)
  throw new Error(`SSR unexpectedly requested ${url}`)
}
useAuthStore.setState({
  httpClient: () => ({
    get: unexpectedRequest,
    post: unexpectedRequest,
    patch: unexpectedRequest,
    delete: unexpectedRequest,
  }),
})
function render(child: ReturnType<typeof createElement>) {
  return renderToStaticMarkup(
    createElement(StaticRouter, { location: '/results/e1' }, child),
  )
}

test('单次运行分区标注运行记录、可用性与面板范围，且服务端不发请求', () => {
  const html = render(
    createElement(AnalysisSection, {
      scope: { kind: 'run', runId: 'run-1' },
      availability: 'partial',
      strategyOptions: ['direct', 'cot'],
    }),
  )
  assert.match(html, /以下统计以运行记录 run-1 为范围/)
  assert.match(html, /以下为当前已记录的部分结果，统计尚非最终结果。/)
  assert.match(html, /范围：本次运行 · 未设置筛选/)
  assert.doesNotMatch(html, /范围：全账号/)
  for (const title of ['成功率统计', 'Token 与费用', '迭代次数', '失败模式'])
    assert.match(html, new RegExp(`aria-label="${title}"`))
  for (const tab of ['统计', '图表', '失败分析', '对比'])
    assert.match(html, new RegExp(`role="tab"[^>]*>${tab}<`))
  assert.doesNotMatch(html, /模型对比/)
  assert.match(html, /aria-label="分析筛选"/)
  assert.match(html, /刷新分析/)
  assert.match(html, /单个标签，精确且区分大小写/)
  assert.match(html, /aria-busy="true"/)
  assert.deepEqual(requests, [])
})

test('全账号分区标注仅已完成运行，只提供按标签成功率与模型对比', () => {
  const html = render(
    createElement(AnalysisSection, { scope: { kind: 'account' } }),
  )
  assert.match(html, /全账号统计只包含已完成的运行，不会按当前任务筛选。/)
  assert.match(html, /范围：全账号 · 仅已完成运行 · 未设置筛选/)
  assert.doesNotMatch(html, /范围：本次运行/)
  for (const tab of ['统计', '图表', '按标签成功率', '模型对比'])
    assert.match(html, new RegExp(`role="tab"[^>]*>${tab}<`))
  assert.doesNotMatch(html, />失败分析<|>对比</)
  assert.deepEqual(requests, [])
})

test('逐题 Token 视图保留同一题目的每次出现并按序列对齐，空值不填零', () => {
  const view = tokenChartView([
    {
      name: 'direct',
      points: [
        { problem_id: 'two-sum', tokens: 10 },
        { problem_id: 'two-sum', tokens: null },
        { problem_id: 'graph', tokens: 7 },
      ],
    },
    {
      name: 'cot',
      points: [
        { problem_id: 'two-sum', tokens: null },
        { problem_id: 'two-sum', tokens: 12 },
        { problem_id: 'two-sum', tokens: 15 },
      ],
    },
  ])
  assert.deepEqual(view.labels, [
    'two-sum',
    'two-sum #2',
    'graph',
    'two-sum #3',
  ])
  assert.deepEqual(view.series, [
    { name: 'direct', values: [10, null, 7, null] },
    { name: 'cot', values: [null, 12, null, 15] },
  ])
  assert.deepEqual(tokenChartView([]), { labels: [], series: [] })
})

test('筛选归一化去掉空白并把空值归为未设置', () => {
  assert.deepEqual(
    normalizeFilters({ strategy: ' cot ', difficulty: '', tag: '   ' }),
    { strategy: 'cot' },
  )
  assert.deepEqual(normalizeFilters({}), {})
})

test('run_id 缺失时只说明不可用，不渲染筛选或面板', () => {
  const html = render(createElement(AnalysisUnavailable))
  assert.match(
    html,
    /运行记录未关联，暂不可分析；不会以评估 ID 代替运行记录发起请求。/,
  )
  assert.doesNotMatch(html, /role="tab"|aria-label="分析筛选"/)
  assert.deepEqual(requests, [])
})
