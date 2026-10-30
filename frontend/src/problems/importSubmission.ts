const terminalImportStatuses = new Set(['completed', 'failed', 'cancelled'])

export function isImportTerminalStatus(status: string): boolean {
  return terminalImportStatuses.has(status)
}

export function canSubmitImport(
  hasFile: boolean,
  busy: boolean,
  progressStatus: string | null,
  submissionLocked = false,
): boolean {
  return (
    hasFile &&
    !busy &&
    !submissionLocked &&
    (progressStatus === null || isImportTerminalStatus(progressStatus))
  )
}
