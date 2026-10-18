export function createRefreshCoordinator<T>(run: () => Promise<T>): {
  refresh(): Promise<T>
} {
  let inflight: Promise<T> | null = null

  return {
    refresh() {
      if (inflight) return inflight
      inflight = run().finally(() => {
        inflight = null
      })
      return inflight
    },
  }
}
