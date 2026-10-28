import { App, Button, Drawer, Input, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext } from 'react-router-dom'
import {
  EmptyState,
  ErrorState,
  Loading,
  ToastExamples,
} from '@/components/common/Feedback.tsx'
import { Icon } from '@/layouts/components/Icon.tsx'
import { useUiStore } from '@/store/ui.ts'
import { appPages } from '@/routes.tsx'
import { DesignFocus } from './DesignFocus.tsx'
import { metrics, runs, type MockRun } from './data.ts'
import { RunList, Status } from './RunList.tsx'
const examples: Record<string, { title: string; description: string }> = {
  '/help': {
    title: '开始一次 LLM 算法评估',
    description:
      '选择题目集 → 选择模型与策略 → 运行并比较结果。仪表盘展示当前账号的真实统计与最近任务；通知仍为 Mock 示例。',
  },
}
export default function BusinessPage() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const actions = useOutletContext<{
    onCreate: () => void
    onImport: () => void
  }>()
  const design = useUiStore((state) => state.appearanceVariant)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [demoState, setDemoState] = useState('ready')
  const [detail, setDetail] = useState<MockRun | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const { message } = App.useApp()
  useEffect(() => () => clearTimeout(timer.current), [])
  const label =
    appPages.find((page) => page.path === pathname)?.label ?? '仪表盘'
  const source =
    pathname === '/results'
      ? runs.filter((run) => run.state === 'completed')
      : runs
  const rows = source.filter(
    (run) =>
      (filter === 'all' || run.state === filter) &&
      `${run.name} ${run.model} ${run.id}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  )
  const clear = () => {
    setQuery('')
    setFilter('all')
  }
  const list = <RunList rows={rows} inspect={setDetail} clear={clear} />
  const retry = () => {
    setDemoState('loading')
    timer.current = setTimeout(() => {
      setDemoState('ready')
      void message.success('Mock 数据已重新加载')
    }, 600)
  }
  const tools = (
    <div className="list-tools">
      <Input
        aria-label="搜索评估任务"
        prefix={<Icon name="search" size={16} />}
        placeholder="搜索任务或模型"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        allowClear
        style={{ maxWidth: 300 }}
      />
      <Select
        aria-label="任务状态"
        value={filter}
        onChange={setFilter}
        options={[
          { value: 'all', label: '全部状态' },
          { value: 'running', label: '运行中' },
          { value: 'completed', label: '已完成' },
          { value: 'failed', label: '失败' },
        ]}
      />
      <span className="muted" role="status">
        {rows.length} 个任务
      </span>
    </div>
  )
  let content
  if (pathname === '/')
    content = (
      <>
        <DesignFocus design={design} go={navigate} inspect={setDetail} />
        <div className="metric-strip">
          <div>
            <span>运行中的评估</span>
            <strong>
              {metrics.running}
              <small>个任务</small>
            </strong>
            <p>112 / 164 道题已执行</p>
          </div>
          <div>
            <span>已完成的评估</span>
            <strong>
              {metrics.complete}
              <small>个任务</small>
            </strong>
            <p>本次 Mock 的任务记录</p>
          </div>
          <div>
            <span>整体 Pass@1</span>
            <strong>
              {((metrics.passed / metrics.total) * 100).toFixed(1)}
              <small>%</small>
            </strong>
            <p>
              {metrics.passed} / {metrics.total} · 仅已完成任务
            </p>
          </div>
          <div>
            <span>累计调用费用</span>
            <strong>
              <small>$</small>
              {metrics.cost.toFixed(2)}
            </strong>
            <p>USD · 当前4个示例任务</p>
          </div>
        </div>
        <div className="work-grid">
          <section className="panel recent">
            <div className="section-head">
              <div>
                <h2>最近评估</h2>
                <p>从任务到结果，追踪每一次运行。</p>
              </div>
              <Button type="text" onClick={() => navigate('/evaluations')}>
                全部任务 <Icon name="arrow" size={16} />
              </Button>
            </div>
            {tools}
            {list}
            <div className="panel-footer">
              <Icon name="clock" size={14} />
              Mock 快照 · 2026-10-20 14:32 CST
            </div>
          </section>
          <aside className="insights">
            <section className="panel comparison">
              <div className="section-head">
                <div>
                  <h2>基线对比</h2>
                  <p>HumanEval · Direct · Pass@1</p>
                </div>
              </div>
              <div className="bar-scale">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </div>
              {runs
                .filter((run) => run.state === 'completed')
                .map((run, i) => (
                  <div className="bar-item" key={run.id}>
                    <div>
                      <span>
                        {i === 0 ? 'Qwen2.5-Coder' : 'DeepSeek-Coder-V2'}
                      </span>
                      <strong>
                        {((run.passed / run.total) * 100).toFixed(1)}%
                      </strong>
                    </div>
                    <div className="bar-track">
                      <div
                        className={i === 0 ? 'bar primary-bar' : 'bar'}
                        style={{ width: `${(run.passed / run.total) * 100}%` }}
                      />
                    </div>
                    <small>
                      {run.passed} / {run.total} 通过
                    </small>
                  </div>
                ))}
              <p className="finding">Qwen 基线领先 4.2 个百分点</p>
              <button
                className="text-link"
                onClick={() => navigate('/results')}
              >
                查看评估结果 <Icon name="arrow" size={16} />
              </button>
            </section>
            <section className="panel attention">
              <div className="section-head">
                <h2>需要关注</h2>
                <span className="attention-dot" />
              </div>
              <h3>1个任务因调用超时中断</h3>
              <p>
                多轮修复策略对照
                <br />
                已保存38 / 100道题的进度。
              </p>
              <Button onClick={() => setDetail(runs[3])}>
                检查失败任务 <Icon name="arrow" size={16} />
              </Button>
            </section>
          </aside>
        </div>
      </>
    )
  else {
    const example = examples[pathname]
    content = (
      <section className="panel example-panel">
        <h2>{example?.title ?? label}</h2>
        <p>{example?.description}</p>
        <Button onClick={actions?.onCreate}>创建评估</Button>
        <p className="sample-caption">布局示例 · 示例内容与通知为 Mock</p>
        {pathname === '/help' && <ToastExamples />}
      </section>
    )
  }
  return (
    <div className="mock-business">
      <div className="page-heading">
        <div>
          <h1>{label}</h1>
          <p>
            {pathname === '/'
              ? {
                  orbit: '每一次运行，都有迹可循。',
                  precision: '让模型差异，清晰可见。',
                  studio: '为每一轮实验留下可比较的记录。',
                }[design]
              : '在统一工作台中管理与比较算法评估。'}
          </p>
        </div>
        <div className="page-actions">
          <Select
            aria-label="预览数据状态"
            value={demoState}
            onChange={(value) => {
              clearTimeout(timer.current)
              setDemoState(value)
            }}
            options={[
              { value: 'ready', label: '状态：正常' },
              { value: 'loading', label: '状态：加载中' },
              { value: 'empty', label: '状态：空数据' },
              { value: 'error', label: '状态：错误' },
            ]}
          />
          <Button
            type="primary"
            onClick={actions?.onCreate}
            icon={<Icon name="plus" size={16} />}
          >
            创建评估
          </Button>
        </div>
      </div>
      {demoState === 'loading' ? (
        <Loading />
      ) : demoState === 'empty' ? (
        <EmptyState onCreate={actions?.onCreate} />
      ) : demoState === 'error' ? (
        <ErrorState onRetry={retry} />
      ) : (
        content
      )}
      <Drawer
        title="评估任务详情 · Mock"
        open={detail !== null}
        onClose={() => setDetail(null)}
        size={480}
      >
        {detail && (
          <>
            <h2>{detail.name}</h2>
            <Status state={detail.state} />
            <dl className="detail-list">
              <dt>任务ID</dt>
              <dd>{detail.id}</dd>
              <dt>模型</dt>
              <dd>{detail.model}</dd>
              <dt>数据集</dt>
              <dd>{detail.dataset}</dd>
              <dt>策略</dt>
              <dd>{detail.strategy}</dd>
              <dt>已执行</dt>
              <dd>
                {detail.done} / {detail.total}
              </dd>
              <dt>调用费用</dt>
              <dd>${detail.cost.toFixed(2)} USD</dd>
            </dl>
            {detail.state === 'failed' && (
              <div className="error-detail" role="alert">
                <h3>模型调用超时 · Mock</h3>
                <p>已保存检查点，示例展示从第39道题恢复。</p>
                <Button
                  onClick={() =>
                    void message.info('恢复操作为 Mock，未提交后端任务')
                  }
                >
                  模拟恢复评估
                </Button>
              </div>
            )}
            <p className="sample-caption">所有任务与结果均为 Mock 数据。</p>
          </>
        )}
      </Drawer>
    </div>
  )
}
