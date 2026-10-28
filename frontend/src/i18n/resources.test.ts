import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import ts from 'typescript'
import enUS from './en-US.ts'
import zhCN from './zh-CN.ts'

const english: Record<string, string> = enUS
const chinese: Record<string, string> = zhCN
const placeholders = (text: string) =>
  [...text.matchAll(/{{(\w+)}}/g)].map((match) => match[1]).sort()

test('catalogs cover referenced keys, preserve interpolation and contain translated English', () => {
  assert.deepEqual(Object.keys(english).sort(), Object.keys(chinese).sort())
  for (const [key, value] of Object.entries(english)) {
    assert.ok(value.trim(), `Empty English translation: ${key}`)
    assert.ok(!/\p{Script=Han}/u.test(value), `Untranslated English: ${key}`)
    assert.deepEqual(
      placeholders(value),
      placeholders(chinese[key]),
      `Interpolation differs: ${key}`,
    )
  }
  function inspect(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) {
        inspect(path)
        continue
      }
      if (!/\.tsx?$/.test(path) || /\.test\.ts$/.test(path)) continue
      const file = ts.createSourceFile(
        path,
        readFileSync(path, 'utf8'),
        ts.ScriptTarget.Latest,
        true,
      )
      function visit(node: ts.Node) {
        if (
          ts.isCallExpression(node) &&
          ts.isIdentifier(node.expression) &&
          node.expression.text === 't' &&
          node.arguments[0] &&
          ts.isStringLiteral(node.arguments[0])
        ) {
          assert.ok(
            Object.hasOwn(english, node.arguments[0].text),
            `Missing key in ${path}: ${node.arguments[0].text}`,
          )
        }
        ts.forEachChild(node, visit)
      }
      visit(file)
    }
  }
  inspect(fileURLToPath(new URL('..', import.meta.url)))
})
