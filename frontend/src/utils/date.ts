const relativeFormatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const shortDateFormatter = new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' })
const fullDateFormatter = new Intl.DateTimeFormat('en', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** "2m ago" / "3h ago" for recent items, falling back to a short date for
 * anything older than a day — matches how modern SaaS boards timestamp cards. */
export function formatRelativeDate(iso: string): string {
  const date = new Date(iso)
  const diffMs = date.getTime() - Date.now()
  const absMs = Math.abs(diffMs)

  if (absMs < MINUTE) return 'just now'
  if (absMs < HOUR) return relativeFormatter.format(Math.round(diffMs / MINUTE), 'minute')
  if (absMs < DAY) return relativeFormatter.format(Math.round(diffMs / HOUR), 'hour')
  return shortDateFormatter.format(date)
}

export function formatFullDate(iso: string): string {
  return fullDateFormatter.format(new Date(iso))
}
