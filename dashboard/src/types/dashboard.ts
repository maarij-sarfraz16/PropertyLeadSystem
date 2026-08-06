export type Metric = {
  label: string
  value: number
  suffix?: string
  change: string
  trend: 'up' | 'down' | 'neutral'
}

export type FeedEventType =
  | 'new_listing'
  | 'ai_extracted'
  | 'duplicate_detected'
  | 'lead_assigned'
  | 'source_scanned'
  | 'high_score'

export type FeedEvent = {
  id: string
  type: FeedEventType
  message: string
  time: string
}

export type SourceStatus = {
  name: string
  status: 'online' | 'offline'
  leadsFound: number
  lastScan: string
  frequency: string
  successRate: number
}

export type LeadStatus = 'new' | 'incomplete' | 'reviewed' | 'assigned' | 'archived'

export type LeadRow = {
  id: string
  title: string
  propertyType?: string | null
  thumbnail?: string | null
  image?: string | null
  city: string
  location: string
  price: number
  currency: string
  bedrooms: number
  area: string
  sellerType: 'owner' | 'agent' | 'unknown'
  score: number
  source: string
  status: LeadStatus
  dateAdded?: string | null
  lastSeen: string
  aiSummary: string
  /** Deep link to the origin advertisement. Null means no verified link exists — never a
   *  homepage or search-page substitute. */
  originalListingUrl?: string | null
  scrapedAt?: string | null
  /** Publish time on the origin platform. */
  postedAt?: string | null
  contactName?: string | null
  contactPhone?: string | null
}

export type LeadDetail = LeadRow & {
  description: string
  images: string[]
  sourcePlatform: string
  originalListingUrl?: string | null
  scrapedAt?: string | null
  metadata: Record<string, unknown>
  aiDetails: {
    intent?: string | null
    confidence?: number | null
    locationText?: string | null
    price?: number | null
    currency?: string | null
    areaValue?: number | null
    areaUnit?: string | null
    bedrooms?: number | null
    sellerType?: string | null
  }
}

export type NotificationItem = {
  id: string
  title: string
  body: string
  level: 'info' | 'warning' | 'critical' | 'success'
  time: string
}

export interface DashboardOverview {
  metrics: Metric[]
  leads: LeadRow[]
  sources: SourceStatus[]
  notifications: NotificationItem[]
  feed: FeedEvent[]
  insights: string[]
  scoring: Array<{ id: string; score: number; label: string; city: string; area: string }>
  pipeline: Array<{ label: string; status: string }>
}
