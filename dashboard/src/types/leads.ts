import type { LeadRow } from './dashboard'

/** Sort orders the backend understands. Kept in lockstep with `_SORTS` in app/api/leads.py. */
export type LeadSort = 'newest' | 'oldest' | 'price_high' | 'price_low' | 'score_high' | 'score_low'

export const SORT_LABELS: Record<LeadSort, string> = {
  newest: 'Newest first',
  oldest: 'Oldest first',
  price_high: 'Highest price',
  price_low: 'Lowest price',
  score_high: 'Highest lead score',
  score_low: 'Lowest lead score',
}

/** Named windows over `first_seen_at`. `custom` defers to the explicit from/to fields. */
export type DatePreset = 'all' | 'today' | 'yesterday' | 'last7' | 'last30' | 'custom'

export const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  all: 'All time',
  today: 'Today',
  yesterday: 'Yesterday',
  last7: 'Last 7 days',
  last30: 'Last 30 days',
  custom: 'Custom range',
}

export interface LeadQuery {
  search: string
  cities: string[]
  sources: string[]
  sellerTypes: string[]
  propertyTypes: string[]
  statuses: string[]
  minScore: number | null
  maxScore: number | null
  datePreset: DatePreset
  /** Only meaningful when datePreset is 'custom'; both are `YYYY-MM-DD` local dates. */
  customFrom: string
  customTo: string
  sort: LeadSort
  page: number
  pageSize: number
}

export const EMPTY_LEAD_QUERY: LeadQuery = {
  search: '',
  cities: [],
  sources: [],
  sellerTypes: [],
  propertyTypes: [],
  statuses: [],
  minScore: null,
  maxScore: null,
  datePreset: 'all',
  customFrom: '',
  customTo: '',
  sort: 'newest',
  page: 1,
  pageSize: 25,
}

export interface LeadPage {
  items: LeadRow[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  hasMore: boolean
}

export interface LeadFacets {
  cities: string[]
  sources: string[]
  sellerTypes: string[]
  propertyTypes: string[]
  statuses: string[]
  priceRange: { min: number; max: number }
  scoreRange: { min: number; max: number }
  dateRange: { earliest: string | null; latest: string | null }
  totalLeads: number
}

export const EMPTY_FACETS: LeadFacets = {
  cities: [],
  sources: [],
  sellerTypes: [],
  propertyTypes: [],
  statuses: [],
  priceRange: { min: 0, max: 0 },
  scoreRange: { min: 0, max: 0 },
  dateRange: { earliest: null, latest: null },
  totalLeads: 0,
}

/**
 * Turn a preset into the absolute instants the backend filters on.
 *
 * Resolved against the *browser's* clock, so "Today" means the user's today rather than UTC's
 * — a lead found at 2am in Karachi belongs to the day the user thinks it does.
 */
export function resolveDateRange(query: LeadQuery): { from: string | null; to: string | null } {
  const startOfDay = (date: Date) => {
    const copy = new Date(date)
    copy.setHours(0, 0, 0, 0)
    return copy
  }
  const endOfDay = (date: Date) => {
    const copy = new Date(date)
    copy.setHours(23, 59, 59, 999)
    return copy
  }
  const today = new Date()

  switch (query.datePreset) {
    case 'today':
      return { from: startOfDay(today).toISOString(), to: endOfDay(today).toISOString() }
    case 'yesterday': {
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)
      return { from: startOfDay(yesterday).toISOString(), to: endOfDay(yesterday).toISOString() }
    }
    case 'last7': {
      const from = new Date(today)
      // Inclusive of today, so "last 7 days" covers 7 calendar days rather than 8.
      from.setDate(from.getDate() - 6)
      return { from: startOfDay(from).toISOString(), to: endOfDay(today).toISOString() }
    }
    case 'last30': {
      const from = new Date(today)
      from.setDate(from.getDate() - 29)
      return { from: startOfDay(from).toISOString(), to: endOfDay(today).toISOString() }
    }
    case 'custom':
      return {
        from: query.customFrom ? startOfDay(new Date(`${query.customFrom}T00:00:00`)).toISOString() : null,
        to: query.customTo ? endOfDay(new Date(`${query.customTo}T00:00:00`)).toISOString() : null,
      }
    default:
      return { from: null, to: null }
  }
}

/** Count of filters actually narrowing the list — drives the "clear filters" affordance. */
export function activeFilterCount(query: LeadQuery): number {
  return (
    (query.search.trim() ? 1 : 0) +
    query.cities.length +
    query.sources.length +
    query.sellerTypes.length +
    query.propertyTypes.length +
    query.statuses.length +
    (query.minScore != null ? 1 : 0) +
    (query.maxScore != null ? 1 : 0) +
    (query.datePreset !== 'all' ? 1 : 0)
  )
}
