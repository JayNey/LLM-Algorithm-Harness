import type { ReactNode } from 'react'

export default function SettingsTable({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div
      className="evaluation-list-scroll"
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <table className="evaluation-list-table" aria-label={label}>
        {children}
      </table>
    </div>
  )
}
