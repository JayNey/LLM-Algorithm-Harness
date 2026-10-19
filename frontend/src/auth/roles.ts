export type UserRole = 'user' | 'admin'

export type RoleState =
  | { status: 'loading' | 'error'; role: null }
  | { status: 'ready'; role: UserRole }

export function readRole(value: unknown): UserRole | null {
  if (typeof value !== 'object' || value === null || !('role' in value))
    return null
  return value.role === 'user' || value.role === 'admin' ? value.role : null
}

export function canAccess(
  role: UserRole | null,
  allowedRoles?: readonly UserRole[],
): boolean {
  return (
    allowedRoles === undefined || (role !== null && allowedRoles.includes(role))
  )
}

export function createRoleLoader(
  read: () => Promise<unknown>,
  update: (state: RoleState) => void,
) {
  let version = 0
  let disposed = false
  return {
    async load() {
      if (disposed) return
      const current = ++version
      update({ status: 'loading', role: null })
      let state: RoleState
      try {
        const role = readRole(await read())
        state = role
          ? { status: 'ready', role }
          : { status: 'error', role: null }
      } catch {
        state = { status: 'error', role: null }
      }
      if (!disposed && version === current) update(state)
    },
    dispose() {
      disposed = true
      version += 1
    },
  }
}
