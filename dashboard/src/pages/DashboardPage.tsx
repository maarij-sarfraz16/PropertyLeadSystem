import type { ReactNode } from 'react'
import { useMemo } from 'react'
import { useState } from 'react'
import { AlertTriangle, RefreshCcw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { AnalyticsPanel } from '../components/AnalyticsPanel'
import { InsightsPanel } from '../components/InsightsPanel'
import { LeadDrawer } from '../components/LeadDrawer'
import { LeadTable } from '../components/LeadTable'
import { LiveFeed } from '../components/LiveFeed'
import { NotificationCenter } from '../components/NotificationCenter'
import { PipelineViz } from '../components/PipelineViz'
import { RadarStats } from '../components/RadarStats'
import { ScoringPanel } from '../components/ScoringPanel'
import { SourceGrid } from '../components/SourceGrid'
import { FadeIn, SectionTitle, SkeletonBlock } from '../components/ui'
import { useDashboardData } from '../hooks/useDashboardData'
import { usePropertyLeads } from '../hooks/usePropertyLeads'
import { fetchPropertyLeadDetail } from '../lib/api'
import type { Role } from '../lib/auth'
import type { LeadDetail } from '../types/dashboard'

type RoleSection = {
  key: string
  title: string
  subtitle: string
  content: ReactNode
}

const sectionMap: Record<Role, RoleSection[]> = {
  admin: [
    { key: 'metrics', title: 'AI Property Radar', subtitle: 'Live metrics across scraping, extraction, and lead quality layers', content: null },
    { key: 'operations', title: 'Live Intelligence Feed', subtitle: 'AI command center event stream', content: null },
    { key: 'scoring', title: 'AI Lead Scoring Panel', subtitle: 'Priority triage by confidence', content: null },
    { key: 'analytics', title: 'Lead Analytics', subtitle: 'Market signals and funnel performance', content: null },
    { key: 'sources', title: 'Source Monitoring Dashboard', subtitle: 'Online/offline state and scan performance', content: null },
    { key: 'pipeline', title: 'AI Extraction Visualization', subtitle: 'Pipeline state from scrape to assignment', content: null },
    { key: 'leads', title: 'Property Lead Table', subtitle: 'Search, filter, sort, paginate, export', content: null },
    { key: 'insights', title: 'AI Insights', subtitle: 'Market-level intelligence generated from live lead flow', content: null },
    { key: 'alerts', title: 'Notification Center', subtitle: 'Alerts across quality, ops, and assignments', content: null },
  ],
  analyst: [
    { key: 'analytics', title: 'Lead analytics', subtitle: 'Trend monitoring and funnel performance', content: null },
    { key: 'queue', title: 'Current lead queue', subtitle: 'Prioritized leads ready for review', content: null },
    { key: 'insights', title: 'Analyst insights', subtitle: 'Live observations from the incoming feed', content: null },
  ],
  agent: [
    { key: 'priority', title: 'Priority leads', subtitle: 'The most relevant opportunities for immediate outreach', content: null },
    { key: 'alerts', title: 'Agent alerts', subtitle: 'Important notices and follow-up reminders', content: null },
    { key: 'actions', title: 'Follow-up actions', subtitle: 'Suggested next moves for hot leads', content: null },
  ],
}

export function DashboardPage({ role }: { role: Role }) {
  const { data, loading, refreshing, error, isUsingFallback, refresh, lastUpdated } = useDashboardData()
  const propertyLeads = usePropertyLeads()
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null)
  const sections = useMemo(() => sectionMap[role], [role])
  const selectedLeadPreview = useMemo<LeadDetail | null>(() => {
    if (!selectedLeadId) return null
    const lead = propertyLeads.data.find((item) => item.id === selectedLeadId)
    if (!lead) return null
    return {
      ...lead,
      description: lead.aiSummary || lead.title,
      images: lead.thumbnail || lead.image ? [lead.thumbnail ?? lead.image ?? ''].filter(Boolean) as string[] : [],
      sourcePlatform: lead.source,
      metadata: {},
      aiDetails: {
        intent: null,
        confidence: null,
        locationText: lead.location,
        price: lead.price,
        currency: 'PKR',
        areaValue: null,
        areaUnit: null,
        bedrooms: lead.bedrooms,
        sellerType: lead.sellerType,
      },
    }
  }, [propertyLeads.data, selectedLeadId])

  const leadDetailQuery = useQuery({
    queryKey: ['property-lead', selectedLeadId],
    queryFn: () => fetchPropertyLeadDetail(selectedLeadId ?? ''),
    enabled: Boolean(selectedLeadId),
    placeholderData: (previousData) => previousData,
  })
  const selectedLead = leadDetailQuery.data ?? selectedLeadPreview
  const pageLoading = loading || propertyLeads.loading

  const header = {
    admin: {
      kicker: 'Admin command center',
      title: 'Executive operations overview',
    },
    analyst: {
      kicker: 'Analyst workspace',
      title: 'Signal analysis and lead triage',
    },
    agent: {
      kicker: 'Agent queue',
      title: 'Fast follow-up and assignment',
    },
  }[role]

  const skeletonCount = role === 'admin' ? 4 : role === 'analyst' ? 3 : 2

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
        <div>
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">{header.kicker}</p>
          <h1 className="text-2xl font-semibold text-white">{header.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
            {refreshing || propertyLeads.refreshing ? 'Syncing...' : `Updated ${lastUpdated}`}
          </span>
          {isUsingFallback ? (
            <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
              Fallback mode
            </span>
          ) : null}
          <button
            onClick={() => void Promise.all([refresh(), propertyLeads.refresh(), leadDetailQuery.refetch()])}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
          >
            <RefreshCcw className="size-4" />
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-400/20 bg-amber-500/10 p-3 text-sm text-amber-200">
          <AlertTriangle className="size-4" />
          {error}
        </div>
      ) : null}

      {propertyLeads.error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">
          <AlertTriangle className="size-4" />
          {propertyLeads.error}
        </div>
      ) : null}

      {pageLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from({ length: skeletonCount }).map((_, index) => (
            <SkeletonBlock key={index} className="h-32" />
          ))}
        </div>
      ) : null}

      {!pageLoading ? (
        <div className="space-y-6">
          {role === 'admin' ? (
            <FadeIn>
              <SectionTitle title="AI Property Radar" subtitle="Live metrics across scraping, extraction, and lead quality layers" />
              {data.metrics.length ? <RadarStats metrics={data.metrics} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No data available.</p>}
            </FadeIn>
          ) : null}

          {sections
            .filter((section) => section.key !== 'metrics')
            .map((section, index) => {
              const content = (() => {
                switch (section.key) {
                  case 'operations':
                    return data.feed.length ? <LiveFeed events={data.feed} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No activity feed available.</p>
                  case 'scoring':
                    return <ScoringPanel rows={data.scoring} />
                  case 'analytics':
                    return <AnalyticsPanel analytics={data.analytics} />
                  case 'sources':
                    return data.sources.length ? <SourceGrid data={data.sources} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No source data available.</p>
                  case 'pipeline':
                    return <PipelineViz stages={data.pipeline} />
                  case 'leads':
                    return propertyLeads.data.length ? <LeadTable leads={propertyLeads.data} onRowClick={(lead) => setSelectedLeadId(lead.id)} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No leads available.</p>
                  case 'insights':
                    return <InsightsPanel insights={data.insights.length ? data.insights : ['No insights available.']} />
                  case 'alerts':
                    return data.notifications.length ? <NotificationCenter items={data.notifications} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No notifications available.</p>
                  case 'queue':
                    return propertyLeads.data.length ? <LeadTable leads={propertyLeads.data} onRowClick={(lead) => setSelectedLeadId(lead.id)} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No leads available.</p>
                  case 'priority':
                    return propertyLeads.data.length ? <LeadTable leads={propertyLeads.data.slice(0, 4)} onRowClick={(lead) => setSelectedLeadId(lead.id)} /> : <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No priority leads available.</p>
                  case 'actions':
                    return <InsightsPanel insights={data.insights.length ? data.insights : ['No follow-up actions available.']} />
                  default:
                    return null
                }
              })()

              return (
                <FadeIn key={section.key} delay={index * 0.04}>
                  <SectionTitle title={section.title} subtitle={section.subtitle} />
                  {content}
                </FadeIn>
              )
            })}
        </div>
      ) : null}

      <LeadDrawer
        lead={selectedLead}
        open={Boolean(selectedLeadId)}
        onClose={() => setSelectedLeadId(null)}
        error={leadDetailQuery.error instanceof Error ? leadDetailQuery.error.message : null}
      />
    </div>
  )
}
