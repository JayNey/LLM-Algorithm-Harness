import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateAlertInput } from '../budgets/client.ts'
import { validateImportFile } from '../problems/client.ts'
import { createLocalization } from './core.ts'

const noStorage = { getItem: () => null, setItem() {} }

test('real dynamic validation messages translate and stored errors switch back to Chinese', async () => {
  const app = createLocalization({ storage: noStorage })
  const messages = [
    ...(['slack', 'webhook', 'smtp'] as const).map((channel) =>
      validateAlertInput({ threshold_pct: 80, channel, target: '' }),
    ),
    validateImportFile({ name: 'problems.yaml', size: 20 }),
  ]
  for (const message of messages) {
    assert.ok(message)
    assert.equal(app.t(message), message)
    await app.changeLanguage('en-US')
    assert.ok(
      !/\p{Script=Han}/u.test(app.t(message)),
      `Untranslated: ${message}`,
    )
    await app.changeLanguage('zh-CN')
    assert.equal(app.t(message), message)
  }
})
