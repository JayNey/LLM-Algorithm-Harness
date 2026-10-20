import { createStore } from 'zustand/vanilla'
export interface MockNotification {
  id: number
  type: '任务完成' | '预算预警' | '系统通知'
  title: string
  text: string
  time: string
  route: '/results' | '/evaluations' | '/help'
  read: boolean
}
const seed: MockNotification[] = [
  {
    id: 1,
    type: '任务完成',
    title: '代码生成基线已完成',
    text: 'HumanEval · 128 / 164 通过',
    time: '13:48',
    route: '/results',
    read: false,
  },
  {
    id: 2,
    type: '预算预警',
    title: '单任务预算使用达 80%',
    text: '多轮修复策略对照 · 请检查调用用量',
    time: '11:04',
    route: '/evaluations',
    read: false,
  },
  {
    id: 3,
    type: '系统通知',
    title: '欢迎使用工作台',
    text: '业务与通知均为 Mock 数据',
    time: '09:00',
    route: '/help',
    read: true,
  },
]
export function createNotificationStore(owner: string) {
  return createStore<{
    owner: string
    notes: MockNotification[]
    markRead: (id: number) => void
    markAllRead: () => void
    clear: () => void
  }>((set) => ({
    owner,
    notes: seed.map((n) => ({ ...n })),
    markRead: (id) =>
      set((state) => ({
        notes: state.notes.map((n) => (n.id === id ? { ...n, read: true } : n)),
      })),
    markAllRead: () =>
      set((state) => ({
        notes: state.notes.map((n) => ({ ...n, read: true })),
      })),
    clear: () => set({ notes: [] }),
  }))
}
