import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRefreshCoordinator } from './refreshCoordinator.ts'

test('并发刷新只执行一次', async () => {
  let calls = 0
  const coordinator = createRefreshCoordinator(async () => {
    calls += 1
    await new Promise((resolve) => setTimeout(resolve, 10))
    return 'next'
  })
  const [first, second] = await Promise.all([
    coordinator.refresh(),
    coordinator.refresh(),
  ])
  assert.equal(calls, 1)
  assert.equal(first, 'next')
  assert.equal(second, 'next')
})

test('刷新失败后可以再次刷新', async () => {
  let calls = 0
  const coordinator = createRefreshCoordinator(async () => {
    calls += 1
    if (calls === 1) throw new Error('fail')
    return 'next'
  })
  await assert.rejects(() => coordinator.refresh(), /fail/)
  assert.equal(await coordinator.refresh(), 'next')
  assert.equal(calls, 2)
})
