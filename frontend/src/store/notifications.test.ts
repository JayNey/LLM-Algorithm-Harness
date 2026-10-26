import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createNotificationStore } from './notifications.ts'

test('通知按类型筛选，已读与清空只改变当前会话', () => {
  const first = createNotificationStore('session-a')
  assert.equal(first.getState().notes.filter((n) => !n.read).length, 2)
  first.getState().markRead(1)
  assert.equal(first.getState().notes.filter((n) => !n.read).length, 1)
  assert.equal(
    first.getState().notes.filter((n) => n.type === '预算预警').length,
    1,
  )
  first.getState().markAllRead()
  assert.equal(first.getState().notes.filter((n) => !n.read).length, 0)
  first.getState().clear()
  assert.equal(first.getState().notes.length, 0)
  const second = createNotificationStore('session-b')
  assert.equal(second.getState().notes.length, 3)
  assert.equal(second.getState().notes.filter((n) => !n.read).length, 2)
})

test('种子通知只指向真实列表或帮助页，不引用虚构详情路由', () => {
  const store = createNotificationStore('session-routes')
  const allowed = new Set(['/results', '/evaluations', '/help'])
  for (const note of store.getState().notes) {
    assert.ok(
      allowed.has(note.route),
      `通知路由必须是真实列表/帮助页：${note.route}`,
    )
  }
  assert.equal(
    store.getState().notes.some((n) => n.text === '示例与通知均为 Mock 数据'),
    true,
  )
})
