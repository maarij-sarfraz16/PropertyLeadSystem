import type { LeadRow } from './dashboard'
import { EMPTY_LEAD_QUERY, type LeadQuery } from './leads'

/**
 * A saved search is the leads filter bar, persisted.
 *
 * `criteria` deliberately uses the same camelCase keys `/api/leads` accepts, so converting
 * between a saved search and the live filter state is a rename-free round trip — and the
 * criteria that fired an alert are exactly the criteria the click-through list applies.
 */
export interface SavedSearch {
  id: string
  name: string
  agentId: string | null
  agentName: string | null
  criteria: Record<string, unknown>
  enabled: boolean
  notifyRealtime: boolean
  matchCount: number
  lastMatchedAt: string | null
  createdAt: string | null
  unreadCount: number
}

export interface AlertNotification {
  id: string
  savedSearchId: string | null
  savedSearchName: string | null
  agentId: string | null
  leadId: string
  title: string | null
  body: string | null
  status: string
  channel: string
  readAt: string | null
  createdAt: string | null
  lead: LeadRow | null
}

export interface Agent {
  id: string
  name: string
  email: string | null
  phone: string | null
  active: boolean
}

export interface SearchPreview {
  total: number
  estimatedPerDay: number | null
  matchable?: boolean
}

/**
 * Keys that are presentation, not matching, and must never be stored.
 *
 * `dateFrom`/`dateTo` are the important ones: the filter bar resolves its date presets to
 * absolute instants before sending them, so persisting them would freeze a search to the day
 * it was created and it would silently stop matching. The backend strips these too — this is
 * the client-side half of the same rule.
 */
const NON_CRITERIA_KEYS = new Set(['dateFrom', 'dateTo', 'sort', 'page', 'pageSize'])

const LIST_KEYS = ['city', 'source', 'sellerType', 'propertyType', 'status'] as const
const NUMBER_KEYS = [
  'minScore',
  'maxScore',
  'minPrice',
  'maxPrice',
  'minBedrooms',
  'maxBedrooms',
] as const

/** Turn the live filter state into a storable criteria object. */
export function leadQueryToCriteria(query: LeadQuery): Record<string, unknown> {
  const criteria: Record<string, unknown> = {}

  if (query.search.trim()) criteria.search = query.search.trim()
  if (query.cities.length) criteria.city = [...query.cities]
  if (query.sources.length) criteria.source = [...query.sources]
  if (query.sellerTypes.length) criteria.sellerType = [...query.sellerTypes]
  if (query.propertyTypes.length) criteria.propertyType = [...query.propertyTypes]
  if (query.statuses.length) criteria.status = [...query.statuses]
  if (query.minScore != null) criteria.minScore = query.minScore
  if (query.maxScore != null) criteria.maxScore = query.maxScore

  return criteria
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

function asNumber(value: unknown): number | null {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Replay stored criteria back into the filter bar. */
export function criteriaToLeadQuery(criteria: Record<string, unknown> | undefined): LeadQuery {
  const source = criteria ?? {}
  return {
    ...EMPTY_LEAD_QUERY,
    search: typeof source.search === 'string' ? source.search : '',
    cities: asStringArray(source.city),
    sources: asStringArray(source.source),
    sellerTypes: asStringArray(source.sellerType),
    propertyTypes: asStringArray(source.propertyType),
    statuses: asStringArray(source.status),
    minScore: asNumber(source.minScore),
    maxScore: asNumber(source.maxScore),
  }
}

/** A short human summary of what a saved search watches, for chips and list rows. */
export function describeCriteria(criteria: Record<string, unknown> | undefined): string {
  const source = criteria ?? {}
  const parts: string[] = []

  for (const key of LIST_KEYS) {
    const values = asStringArray(source[key])
    if (values.length) parts.push(values.join(', '))
  }
  if (typeof source.search === 'string' && source.search) parts.push(`"${source.search}"`)

  const min = asNumber(source.minPrice)
  const max = asNumber(source.maxPrice)
  if (min != null || max != null) {
    const fmt = (value: number) => `${(value / 1_000_000).toFixed(1)}M`
    parts.push(
      min != null && max != null
        ? `${fmt(min)}-${fmt(max)}`
        : min != null
          ? `over ${fmt(min)}`
          : `under ${fmt(max as number)}`,
    )
  }

  const minScore = asNumber(source.minScore)
  if (minScore != null) parts.push(`score ${minScore}+`)

  return parts.join(' · ') || 'All leads'
}

/** Mirrors the server's `is_matchable`, so the save button never submits a guaranteed 422. */
export function isMatchable(criteria: Record<string, unknown> | undefined): boolean {
  const source = criteria ?? {}
  if (typeof source.search === 'string' && source.search.trim()) return true
  if (LIST_KEYS.some((key) => key !== 'status' && asStringArray(source[key]).length)) return true
  return NUMBER_KEYS.some((key) => asNumber(source[key]) != null)
}

export { NON_CRITERIA_KEYS }
