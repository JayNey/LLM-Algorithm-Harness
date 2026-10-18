export function sanitizeReturnPath(value: string | null | undefined): string {
  if (
    value === null ||
    value === undefined ||
    !value.startsWith('/') ||
    value.startsWith('//')
  ) {
    return '/'
  }
  if (value.includes('://') || value.includes('\\')) {
    return '/'
  }
  return value
}
