import assert from 'node:assert/strict'
import { test } from 'node:test'
import { recordCheck } from '../../scripts/fixture-checks.mjs'

test('unawaited synchronous checks finish before the fixture can report success', async () => {
  const rows: { name: string; pass: boolean }[] = []
  const completion = recordCheck(rows, 'sync', () => {})
  const finishedSynchronously = rows[0].pass
  await completion
  assert.equal(finishedSynchronously, true)
})

test('a synchronous failure reaches the scenario catch without awaiting', async () => {
  const rows: { pass: boolean }[] = []
  const failure = new Error('fixture must fail')
  let caught: unknown
  let completion
  try {
    completion = recordCheck(rows, 'sync failure', () => {
      throw failure
    })
  } catch (error) {
    caught = error
  }
  if (completion) await completion.catch(() => {})
  assert.equal(caught, failure)
  assert.equal(rows[0].pass, false)
})

test('an asynchronous check stays pending and rejected work reaches its awaiter', async () => {
  const rows: { pass: boolean }[] = []
  let reject!: (error: Error) => void
  const failure = new Error('async failure')
  const done = recordCheck(
    rows,
    'async failure',
    () =>
      new Promise((_, fail) => {
        reject = fail
      }),
  )
  await Promise.resolve()
  assert.equal(rows[0].pass, false)
  reject(failure)
  await assert.rejects(done, (error: unknown) => error === failure)
  assert.equal(rows[0].pass, false)
})

test('an asynchronous success becomes passed only after completion', async () => {
  const rows: { pass: boolean }[] = []
  let resolve!: () => void
  const done = recordCheck(
    rows,
    'async success',
    () =>
      new Promise<void>((yes) => {
        resolve = yes
      }),
  )
  await Promise.resolve()
  assert.equal(rows[0].pass, false)
  resolve()
  await done
  assert.equal(rows[0].pass, true)
})
