import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as ui from './ui.ts'

function storage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
  }
}

test('三种风格分别恢复主题，折叠和外观跨重建保存', () => {
  assert.equal(typeof ui.createUiStore, 'function')
  const box = storage()
  const store = ui.createUiStore({ storage: box, systemDark: false })
  assert.equal(store.getState().appearanceVariant, 'orbit')
  assert.equal(store.getState().colorScheme, 'dark')
  store.getState().setThemePreference('light')
  store.getState().setAppearanceVariant('precision')
  store.getState().setThemePreference('dark')
  store.getState().setAppearanceVariant('orbit')
  assert.equal(store.getState().colorScheme, 'light')
  store.getState().toggleSidebar()
  const restored = ui.createUiStore({ storage: box, systemDark: false })
  assert.equal(restored.getState().appearanceVariant, 'orbit')
  assert.equal(restored.getState().sidebarCollapsed, true)
  restored.getState().setAppearanceVariant('precision')
  assert.equal(restored.getState().colorScheme, 'dark')
})

test('系统变化只影响跟随系统的主题，非法偏好与不可用存储安全降级', () => {
  assert.equal(typeof ui.createUiStore, 'function')
  const box = storage()
  box.setItem(
    'llm-harness-ui',
    JSON.stringify({
      appearanceVariant: '__proto__',
      themes: { orbit: 'invalid' },
    }),
  )
  const store = ui.createUiStore({ storage: box, systemDark: false })
  assert.equal(store.getState().appearanceVariant, 'orbit')
  store.getState().setThemePreference('system')
  store.getState().setSystemDark(true)
  assert.equal(store.getState().colorScheme, 'dark')
  store.getState().setThemePreference('light')
  store.getState().setSystemDark(true)
  assert.equal(store.getState().colorScheme, 'light')
  const blocked = ui.createUiStore({
    storage: {
      getItem() {
        throw Error('blocked')
      },
      setItem() {
        throw Error('blocked')
      },
    },
  })
  assert.doesNotThrow(() => blocked.getState().toggleColorScheme())
  assert.doesNotThrow(() => blocked.getState().toggleSidebar())
})
