const replacements: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
  '/': '&#47;',
}

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"'/]/g, (char) => replacements[char] ?? char)
}
