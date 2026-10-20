import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  clearSession,
  readSession,
  writeSession,
  type StoredSession,
} from './tokenStore.ts'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  }
}

const session: StoredSession = {
  marker: 'marker',
  expiresAt: 1_700_000_000_000,
  username: null,
}

test('记住我只写入 localStorage，且不保存令牌', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  assert.equal(readSession(storages)?.marker, 'marker')
  assert.equal(storages.session.length, 0)
  assert.equal(
    storages.local.getItem('llm-harness-session')?.includes('accessToken'),
    false,
  )
})

test('含令牌的旧会话不能恢复', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  storages.local.setItem(
    'llm-harness-session',
    JSON.stringify({
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresAt: 1,
      username: null,
    }),
  )
  assert.equal(readSession(storages), null)
})

test('不记住我只写入 sessionStorage，恢复时不读旧的 localStorage', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  writeSession(false, { ...session, marker: 'tab' }, storages)
  assert.equal(readSession(storages)?.marker, 'tab')
  assert.equal(storages.local.length, 0)
})

test('清除两边后不能恢复', () => {
  const storages = { local: memoryStorage(), session: memoryStorage() }
  writeSession(true, session, storages)
  clearSession(storages)
  assert.equal(readSession(storages), null)
})
