/** Presentation helpers shared by the leads list and the detail view. */

const DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/**
 * Prices in the South Asian convention the listings themselves use.
 *
 * A Pakistani property ad says "4.75 crore", never "47,500,000" — showing the raw number
 * forces the reader to count digits. The exact figure stays available as a tooltip.
 */
export function formatPrice(value: number, currency = 'PKR'): string {
  if (!value) return 'Price not listed'
  if (value >= 10_000_000) return `${currency} ${trim(value / 10_000_000)} crore`
  if (value >= 100_000) return `${currency} ${trim(value / 100_000)} lakh`
  return `${currency} ${value.toLocaleString('en-US')}`
}

export function formatPriceExact(value: number, currency = 'PKR'): string {
  return value ? `${currency} ${value.toLocaleString('en-US')}` : 'Not listed'
}

function trim(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '')
}

export function formatDateTime(value?: string | null): string {
  if (!value) return 'Unknown'
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? value : DATE_TIME.format(parsed)
}

export function formatRelative(value?: string | null): string {
  if (!value) return ''
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return ''
  const seconds = (Date.now() - parsed) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 2_592_000) return `${Math.floor(seconds / 86_400)}d ago`
  return `${Math.floor(seconds / 2_592_000)}mo ago`
}

export function scoreTone(score: number): 'critical' | 'info' | 'warning' | 'default' {
  if (score >= 85) return 'critical'
  if (score >= 70) return 'info'
  if (score >= 40) return 'warning'
  return 'default'
}

export function scoreLabel(score: number): string {
  if (score >= 85) return 'Hot'
  if (score >= 70) return 'High'
  if (score >= 40) return 'Medium'
  return 'Low'
}
