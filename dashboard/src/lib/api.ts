import type { DashboardOverview, LeadDetail, LeadRow, LeadStatus } from '../types/dashboard'
import type { LeadFacets, LeadPage, LeadQuery } from '../types/leads'
import { EMPTY_FACETS, resolveDateRange } from '../types/leads'
import type {
  Agent,
  AlertNotification,
  SavedSearch,
  SearchPreview,
} from '../types/savedSearches'

export type { DashboardOverview } from '../types/dashboard'

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

const LEAD_STATUSES: LeadStatus[] = ['new', 'reviewed', 'assigned', 'archived']

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`)
  }
  return (await response.json()) as T
}

/**
 * POST/PATCH/DELETE with a JSON body.
 *
 * Surfaces the server's `detail` message rather than a bare status code, because the saved
 * search endpoints reject a too-broad search with an explanation the user needs to read.
 */
async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    let detail = `Request failed with ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload?.detail) detail = payload.detail
    } catch {
      // Non-JSON error body; the status-code message stands.
    }
    throw new Error(detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * Endpoints for the realtime channels. The WebSocket URL is derived from the API base so a
 * single VITE_API_URL configures both, and https automatically implies wss.
 */
export function streamUrls(topics?: string[]): { ws: string; sse: string } {
  const base = new URL(API_BASE_URL, window.location.origin)
  const wsProtocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  // Omitting topics subscribes to everything, which is the shared-instance default.
  const query = topics?.length ? `?topics=${encodeURIComponent(topics.join(','))}` : ''
  return {
    ws: `${wsProtocol}//${base.host}/ws/leads${query}`,
    sse: `${base.origin}/api/stream${query}`,
  }
}

function emptyOverview(): DashboardOverview {
  return {
    metrics: [],
    leads: [],
    sources: [],
    notifications: [],
    feed: [],
    insights: [],
    scoring: [],
    pipeline: [],
  }
}

function normalizeOverview(payload: Partial<DashboardOverview> | undefined): DashboardOverview {
  const safe = payload ?? {}
  return {
    metrics: safe.metrics ?? [],
    leads: safe.leads ?? [],
    sources: safe.sources ?? [],
    notifications: safe.notifications ?? [],
    feed: safe.feed ?? [],
    insights: safe.insights ?? [],
    scoring: safe.scoring ?? [],
    pipeline: safe.pipeline ?? [],
  }
}

/**
 * Exported because the realtime stream pushes the same row shape the REST endpoint returns,
 * and both must be normalized identically — otherwise a streamed lead and a refetched lead
 * would render differently.
 */
export function normalizeLeadRow(payload: Partial<LeadRow> | undefined): LeadRow {
  const safe = payload ?? {}
  return {
    id: String(safe.id ?? ''),
    title: String(safe.title ?? 'Property listing'),
    propertyType: safe.propertyType ?? null,
    thumbnail: safe.thumbnail ?? safe.image ?? null,
    image: safe.image ?? safe.thumbnail ?? null,
    city: String(safe.city ?? 'Unknown'),
    location: String(safe.location ?? 'Unknown'),
    price: Number(safe.price ?? 0),
    currency: String(safe.currency ?? 'PKR'),
    bedrooms: Number(safe.bedrooms ?? 0),
    area: String(safe.area ?? ''),
    sellerType: safe.sellerType === 'agent' || safe.sellerType === 'owner' ? safe.sellerType : 'unknown',
    score: Number(safe.score ?? 0),
    source: String(safe.source ?? 'Unknown'),
    status: LEAD_STATUSES.includes(safe.status as LeadStatus) ? (safe.status as LeadStatus) : 'new',
    dateAdded: safe.dateAdded ?? null,
    lastSeen: String(safe.lastSeen ?? safe.dateAdded ?? 'Unknown'),
    aiSummary: String(safe.aiSummary ?? ''),
    originalListingUrl: safe.originalListingUrl ?? null,
    scrapedAt: safe.scrapedAt ?? null,
    postedAt: safe.postedAt ?? null,
    contactName: safe.contactName ?? null,
    contactPhone: safe.contactPhone ?? null,
  }
}

function normalizeLeadDetail(payload: Partial<LeadDetail> | undefined): LeadDetail {
  const safe = normalizeLeadRow(payload)
  const detail = payload ?? {}
  return {
    ...safe,
    description: String(detail.description ?? safe.aiSummary ?? ''),
    images: Array.isArray(detail.images) ? detail.images.filter((image): image is string => Boolean(image)) : [],
    sourcePlatform: String(detail.sourcePlatform ?? safe.source ?? 'Unknown'),
    originalListingUrl: detail.originalListingUrl ?? safe.originalListingUrl ?? null,
    scrapedAt: detail.scrapedAt ?? safe.scrapedAt ?? null,
    metadata: (detail.metadata ?? {}) as Record<string, unknown>,
    aiDetails: {
      intent: detail.aiDetails?.intent ?? null,
      confidence: detail.aiDetails?.confidence ?? null,
      locationText: detail.aiDetails?.locationText ?? null,
      price: detail.aiDetails?.price ?? null,
      currency: detail.aiDetails?.currency ?? null,
      areaValue: detail.aiDetails?.areaValue ?? null,
      areaUnit: detail.aiDetails?.areaUnit ?? null,
      bedrooms: detail.aiDetails?.bedrooms ?? null,
      sellerType: detail.aiDetails?.sellerType ?? null,
    },
  }
}

export async function fetchDashboardOverview(): Promise<{
  data: DashboardOverview
  error: string | null
  isUsingFallback: boolean
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/dashboard/overview`, {
      headers: { Accept: 'application/json' },
    })

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`)
    }

    const payload = (await response.json()) as Partial<DashboardOverview>
    return { data: normalizeOverview(payload), error: null, isUsingFallback: false }
  } catch (error) {
    console.warn('Dashboard API unavailable.', error)
    return {
      data: emptyOverview(),
      error: 'Backend service unavailable. No data available.',
      isUsingFallback: true,
    }
  }
}

/**
 * Translate the UI's filter state into the query string `/api/leads` expects.
 *
 * Multi-select filters are sent as repeated params (`?city=Lahore&city=Karachi`) — the shape
 * FastAPI parses into a list. Empty values are omitted entirely so an unset filter never
 * reaches the backend as an empty-string predicate that matches nothing.
 */
export function leadQueryToSearchParams(query: LeadQuery): URLSearchParams {
  const params = new URLSearchParams()
  const append = (key: string, values: string[]) => {
    values.filter(Boolean).forEach((value) => params.append(key, value))
  }

  if (query.search.trim()) params.set('search', query.search.trim())
  append('city', query.cities)
  append('source', query.sources)
  append('sellerType', query.sellerTypes)
  append('propertyType', query.propertyTypes)
  append('status', query.statuses)
  if (query.minScore != null) params.set('minScore', String(query.minScore))
  if (query.maxScore != null) params.set('maxScore', String(query.maxScore))

  const { from, to } = resolveDateRange(query)
  if (from) params.set('dateFrom', from)
  if (to) params.set('dateTo', to)

  params.set('sort', query.sort)
  params.set('page', String(query.page))
  params.set('pageSize', String(query.pageSize))
  return params
}

export async function fetchLeadPage(query: LeadQuery): Promise<LeadPage> {
  const payload = await getJson<Partial<LeadPage> & { items?: Array<Partial<LeadRow>> }>(
    `/api/leads?${leadQueryToSearchParams(query).toString()}`,
  )

  const items = (payload.items ?? []).map((item) => normalizeLeadRow(item))
  const pageSize = Number(payload.pageSize ?? query.pageSize)
  const total = Number(payload.total ?? items.length)
  return {
    items,
    total,
    page: Number(payload.page ?? query.page),
    pageSize,
    totalPages: Number(payload.totalPages ?? Math.max(1, Math.ceil(total / pageSize))),
    hasMore: Boolean(payload.hasMore),
  }
}

export async function fetchLeadFacets(): Promise<LeadFacets> {
  const payload = await getJson<Partial<LeadFacets>>('/api/leads/facets')
  return {
    ...EMPTY_FACETS,
    ...payload,
    cities: payload.cities ?? [],
    sources: payload.sources ?? [],
    sellerTypes: payload.sellerTypes ?? [],
    propertyTypes: payload.propertyTypes ?? [],
    statuses: payload.statuses ?? [],
  }
}

/** Flat list used by the overview widgets, which show a fixed slice rather than a page. */
export async function fetchPropertyLeads(limit = 50): Promise<LeadRow[]> {
  const payload = await getJson<{ items?: Array<Partial<LeadRow>> }>(
    `/api/leads?page=1&pageSize=${limit}&sort=newest`,
  )
  return (payload.items ?? []).map((item) => normalizeLeadRow(item))
}

export async function fetchPropertyLeadDetail(leadId: string): Promise<LeadDetail> {
  const payload = await getJson<Partial<LeadDetail>>(`/api/leads/${encodeURIComponent(leadId)}`)
  return normalizeLeadDetail(payload)
}

export async function updateLeadStatus(leadId: string, status: LeadStatus): Promise<LeadStatus> {
  const response = await fetch(`${API_BASE_URL}/api/leads/${encodeURIComponent(leadId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ status }),
  })

  if (!response.ok) {
    throw new Error(`Could not update status (${response.status})`)
  }

  const payload = (await response.json()) as { status?: string }
  return (payload.status as LeadStatus) ?? status
}

// -- saved searches, alerts and agents ---------------------------------------
// The alert inbox is the source of truth for what matched; the realtime stream is only a
// faster path to the same rows. Every list endpoint therefore returns complete data rather
// than deltas, so a client that missed a push recovers on its next poll.

export async function fetchSavedSearches(agentId?: string): Promise<SavedSearch[]> {
  const query = agentId ? `?agentId=${encodeURIComponent(agentId)}` : ''
  const payload = await getJson<{ items?: SavedSearch[] }>(`/api/saved-searches${query}`)
  return payload.items ?? []
}

export function createSavedSearch(input: {
  name: string
  criteria: Record<string, unknown>
  agentId?: string | null
  notifyRealtime?: boolean
}): Promise<SavedSearch> {
  return sendJson<SavedSearch>('/api/saved-searches', 'POST', input)
}

export function updateSavedSearch(
  id: string,
  patch: Partial<{
    name: string
    criteria: Record<string, unknown>
    agentId: string | null
    enabled: boolean
    notifyRealtime: boolean
  }>,
): Promise<SavedSearch> {
  return sendJson<SavedSearch>(`/api/saved-searches/${encodeURIComponent(id)}`, 'PATCH', patch)
}

export function deleteSavedSearch(id: string): Promise<{ deleted: boolean }> {
  return sendJson<{ deleted: boolean }>(`/api/saved-searches/${encodeURIComponent(id)}`, 'DELETE')
}

/** How noisy a set of criteria would be, asked *before* the search is saved. */
export function previewCriteria(criteria: Record<string, unknown>): Promise<SearchPreview> {
  return sendJson<SearchPreview>('/api/saved-searches/preview', 'POST', { criteria })
}

export async function fetchNotifications(options: {
  unreadOnly?: boolean
  savedSearchId?: string
  limit?: number
} = {}): Promise<AlertNotification[]> {
  const params = new URLSearchParams()
  if (options.unreadOnly) params.set('unreadOnly', 'true')
  if (options.savedSearchId) params.set('savedSearchId', options.savedSearchId)
  params.set('limit', String(options.limit ?? 50))

  const payload = await getJson<{ items?: Array<Partial<AlertNotification>> }>(
    `/api/notifications?${params.toString()}`,
  )
  return (payload.items ?? []).map((item) => ({
    ...(item as AlertNotification),
    lead: item.lead ? normalizeLeadRow(item.lead) : null,
  }))
}

export function fetchUnreadCount(): Promise<{ count: number; bySearch: Record<string, number> }> {
  return getJson<{ count: number; bySearch: Record<string, number> }>(
    '/api/notifications/unread-count',
  )
}

export function markNotificationRead(id: string): Promise<{ id: string }> {
  return sendJson<{ id: string }>(`/api/notifications/${encodeURIComponent(id)}/read`, 'POST')
}

export function markAllNotificationsRead(savedSearchId?: string): Promise<{ updated: number }> {
  const query = savedSearchId ? `?savedSearchId=${encodeURIComponent(savedSearchId)}` : ''
  return sendJson<{ updated: number }>(`/api/notifications/read-all${query}`, 'POST')
}

export async function fetchAgents(): Promise<Agent[]> {
  const payload = await getJson<{ items?: Agent[] }>('/api/agents')
  return payload.items ?? []
}

export function createAgent(input: {
  name: string
  email?: string
  phone?: string
}): Promise<Agent> {
  return sendJson<Agent>('/api/agents', 'POST', input)
}
