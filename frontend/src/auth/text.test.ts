import assert from 'node:assert/strict'
import { test } from 'node:test'
import { escapeHtml } from './text.ts'

test('HTML 元字符被转义且不重复转义 &', () => {
  assert.equal(
    escapeHtml(`<script>a&b"'/</script>`),
    '&lt;script&gt;a&amp;b&quot;&#39;&#47;&lt;&#47;script&gt;',
  )
  assert.equal(escapeHtml('ada'), 'ada')
})
