export interface MockRun {
  id: string
  name: string
  model: string
  dataset: string
  strategy: string
  state: 'running' | 'completed' | 'failed'
  done: number
  total: number
  passed: number
  cost: number
  time: string
}
// Entirely fictitious, local-only data. Metrics are computed from these rows.
export const runs: MockRun[] = [
  {
    id: 'eval-024',
    name: '推理策略消融实验',
    model: 'Qwen2.5-Coder-32B',
    dataset: 'HumanEval',
    strategy: 'Reflexion',
    state: 'running',
    done: 112,
    total: 164,
    passed: 91,
    cost: 1.42,
    time: '14:32',
  },
  {
    id: 'eval-023',
    name: '代码生成基线 · Qwen',
    model: 'Qwen2.5-Coder-32B',
    dataset: 'HumanEval',
    strategy: 'Direct',
    state: 'completed',
    done: 164,
    total: 164,
    passed: 128,
    cost: 1.86,
    time: '13:48',
  },
  {
    id: 'eval-022',
    name: '代码生成基线 · DeepSeek',
    model: 'DeepSeek-Coder-V2',
    dataset: 'HumanEval',
    strategy: 'Direct',
    state: 'completed',
    done: 164,
    total: 164,
    passed: 121,
    cost: 1.18,
    time: '12:16',
  },
  {
    id: 'eval-021',
    name: '多轮修复策略对照',
    model: 'Qwen2.5-Coder-32B',
    dataset: 'MBPP',
    strategy: 'Self-refine',
    state: 'failed',
    done: 38,
    total: 100,
    passed: 25,
    cost: 0.38,
    time: '11:05',
  },
]
export const metrics = {
  running: runs.filter((r) => r.state === 'running').length,
  complete: runs.filter((r) => r.state === 'completed').length,
  cost: runs.reduce((s, r) => s + Math.round(r.cost * 100), 0) / 100,
  passed: runs
    .filter((r) => r.state === 'completed')
    .reduce((s, r) => s + r.passed, 0),
  total: runs
    .filter((r) => r.state === 'completed')
    .reduce((s, r) => s + r.total, 0),
}
