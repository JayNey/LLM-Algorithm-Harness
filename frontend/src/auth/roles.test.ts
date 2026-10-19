import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canAccess, createRoleLoader, readRole } from './roles.ts'

test('只接受后端明确返回的两种角色', () => {
  assert.equal(readRole({ role: 'admin' }), 'admin')
  assert.equal(readRole({ role: 'user' }), 'user')
  for (const value of [null, {}, { role: 'owner' }, { is_admin: true }]) {
    assert.equal(readRole(value), null)
  }
})

test('管理员路由默认拒绝，普通页面无需等待角色', () => {
  assert.equal(canAccess(null), true)
  assert.equal(canAccess(null, ['admin']), false)
  assert.equal(canAccess('user', ['admin']), false)
  assert.equal(canAccess('admin', ['admin']), true)
  assert.equal(canAccess('admin', []), false)
})

test('角色查询失败和未知角色都关闭访问，并允许重试', async () => {
  let attempts = 0
  const states: unknown[] = []
  const loader = createRoleLoader(
    async () => {
      attempts += 1
      if (attempts === 1) throw new Error('offline')
      if (attempts === 2) return { role: 'owner' }
      return { role: 'admin' }
    },
    (state) => states.push(state),
  )
  await loader.load()
  assert.deepEqual(states.at(-1), { status: 'error', role: null })
  await loader.load()
  assert.deepEqual(states.at(-1), { status: 'error', role: null })
  await loader.load()
  assert.deepEqual(states.at(-1), { status: 'ready', role: 'admin' })
})

test('登出卸载后忽略迟到的管理员响应', async () => {
  let finish!: (value: unknown) => void
  const states: unknown[] = []
  const loader = createRoleLoader(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
    (state) => states.push(state),
  )
  const pending = loader.load()
  loader.dispose()
  finish({ role: 'admin' })
  await pending
  assert.deepEqual(states, [{ status: 'loading', role: null }])
})

test('后发查询撤销角色后，先前管理员响应不能覆盖结果', async () => {
  const finishes: ((value: unknown) => void)[] = []
  const states: unknown[] = []
  const loader = createRoleLoader(
    () =>
      new Promise((resolve) => {
        finishes.push(resolve)
      }),
    (state) => states.push(state),
  )
  const first = loader.load()
  const second = loader.load()
  finishes[1]({ role: 'user' })
  await second
  finishes[0]({ role: 'admin' })
  await first
  assert.deepEqual(states.at(-1), { status: 'ready', role: 'user' })
})
