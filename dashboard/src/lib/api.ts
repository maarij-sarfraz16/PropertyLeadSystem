import type { DashboardOverview, LeadDetail, LeadRow } from '../types/dashboard'

export type { DashboardOverview } from '../types/dashboard'

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

function emptyOverview(): DashboardOverview {
  return {
    metrics: [],
    leads: [],
    sources: [],
    notifications: [],
    feed: [],
    analytics: {
      dailyLeads: [],
      cityLeads: [],
      sourceLeads: [],
      intentMix: [],
      sellerMix: [],
      priceDistribution: [],
      conversion: [],
    },
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
    analytics: safe.analytics ?? {
      dailyLeads: [],
      cityLeads: [],
      sourceLeads: [],
      intentMix: [],
      sellerMix: [],
      priceDistribution: [],
      conversion: [],
    },
    insights: safe.insights ?? [],
    scoring: safe.scoring ?? [],
    pipeline: safe.pipeline ?? [],
  }
}

function normalizeLeadRow(payload: Partial<LeadRow> | undefined): LeadRow {
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
    bedrooms: Number(safe.bedrooms ?? 0),
    area: String(safe.area ?? ''),
    sellerType: safe.sellerType === 'agent' || safe.sellerType === 'owner' ? safe.sellerType : 'unknown',
    score: Number(safe.score ?? 0),
    source: String(safe.source ?? 'Unknown'),
    status: safe.status === 'reviewed' || safe.status === 'assigned' ? safe.status : 'new',
    dateAdded: safe.dateAdded ?? null,
    lastSeen: String(safe.lastSeen ?? safe.dateAdded ?? 'Unknown'),
    aiSummary: String(safe.aiSummary ?? ''),
    originalListingUrl: safe.originalListingUrl ?? null,
    scrapedAt: safe.scrapedAt ?? null,
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

export async function fetchPropertyLeads(): Promise<LeadRow[]> {
  const response = await fetch(`${API_BASE_URL}/api/leads`, {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`)
  }

  const payload = (await response.json()) as Array<Partial<LeadRow>>
  return payload.map((item) => normalizeLeadRow(item))
}

export async function fetchPropertyLeadDetail(leadId: string): Promise<LeadDetail> {
  const response = await fetch(`${API_BASE_URL}/api/leads/${encodeURIComponent(leadId)}`, {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`)
  }

  const payload = (await response.json()) as Partial<LeadDetail>
  return normalizeLeadDetail(payload)
}
