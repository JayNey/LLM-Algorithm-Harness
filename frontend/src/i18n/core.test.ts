import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as core from './core.ts'

function storage(initial?: string) {
  const values = new Map<string, string>()
  if (initial !== undefined) values.set('llm-harness-language', initial)
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
  }
}

test('explicit language survives reconstruction and invalid preferences default to Chinese', async () => {
  assert.equal(typeof core.createLocalization, 'function')
  for (const initial of [undefined, 'broken', '__proto__', 'en-GB', '{']) {
    const box = storage(initial)
    const app = core.createLocalization({ storage: box })
    assert.equal(app.language, 'zh-CN')
    assert.equal(app.t('登录'), '登录')
    await app.changeLanguage('en-US')
    assert.equal(app.t('登录'), 'Sign in')
    assert.equal(core.createLocalization({ storage: box }).language, 'en-US')
    await app.changeLanguage('invalid')
    assert.equal(app.language, 'en-US')
  }
})

test('blocked storage preserves in-memory language changes', async () => {
  assert.equal(typeof core.createLocalization, 'function')
  const app = core.createLocalization({
    storage: {
      getItem() {
        throw Error('blocked')
      },
      setItem() {
        throw Error('blocked')
      },
    },
  })
  assert.equal(app.language, 'zh-CN')
  await app.changeLanguage('en-US')
  assert.equal(app.language, 'en-US')
  assert.equal(app.t('密码'), 'Password')
  await app.changeLanguage('zh-CN')
  assert.equal(app.t('密码'), '密码')
})

test('translations interpolate literal values and missing keys have readable fallbacks', async () => {
  assert.equal(typeof core.createLocalization, 'function')
  const app = core.createLocalization({ storage: storage('en-US') })
  assert.equal(
    app.t('欢迎回来，{{name}}', { name: '<b>Ada</b>' }),
    'Welcome back, <b>Ada</b>',
  )
  assert.equal(app.t('尚未收录的文案'), '尚未收录的文案')
  let changes = 0
  const listener = () => {
    changes += 1
  }
  app.on('languageChanged', listener)
  await app.changeLanguage('zh-CN')
  assert.equal(app.t('欢迎回来，{{name}}', { name: 'Ada' }), '欢迎回来，Ada')
  assert.equal(changes, 1)
  app.off('languageChanged', listener)
})
