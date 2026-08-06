import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Download, Inbox, RefreshCcw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { LeadDrawer } from '../components/LeadDrawer'
import { LeadFilterBar } from '../components/leads/LeadFilterBar'
import { LeadList } from '../components/leads/LeadList'
import { SaveSearchButton } from '../components/leads/SaveSearchButton'
import { SavedSearchList } from '../components/leads/SavedSearchList'
import { ToastHost } from '../components/ToastHost'
import { SkeletonBlock } from '../components/ui'
import { useLeadStream } from '../hooks/useLeadStream'
import { useLeads } from '../hooks/useLeads'
import { useSavedSearches } from '../hooks/useSavedSearches'
import { fetchPropertyLeadDetail } from '../lib/api'
import { formatDateTime } from '../lib/format'
import type { LeadDetail, LeadStatus } from '../types/dashboard'
import { activeFilterCount } from '../types/leads'
import { criteriaToLeadQuery, type SavedSearch } from '../types/savedSearches'

/**
 * Dedicated lead management workspace.
 *
 * Deliberately carries no metrics, charts or feeds — those live on the overview. Everything
 * here serves one loop: narrow the list, scan it, open a lead, act on it. All narrowing runs
 * server-side (see `useLeads`), so the list covers the entire lead history rather than a
 * recently-fetched window.
 */
export function LeadsPage() {
  const {
    query,
    searchInput,
    setSearchInput,
    patchQuery,
    toggleFilter,
    reset,
    setPage,
    leads,
    total,
    totalPages,
    range,
    facets,
    loading,
    refreshing,
    error,
    refresh,
    setStatus,
    statusPending,
  } = useLeads()

  const stream = useLeadStream()
  const savedSearches = useSavedSearches()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null)

  // Opening an alert from the bell routes here with ?lead=<id>. Consume it once and strip it,
  // so a later manual close does not immediately reopen on the next render.
  const requestedLeadId = searchParams.get('lead')
  useEffect(() => {
    if (!requestedLeadId) return
    setSelectedLeadId(requestedLeadId)
    searchParams.delete('lead')
    setSearchParams(searchParams, { replace: true })
  }, [requestedLeadId, searchParams, setSearchParams])

  /** Loading a saved search replaces the filter state wholesale, so stale filters cannot
   *  survive alongside the ones the alert actually matched on. */
  const applySavedSearch = (search: SavedSearch) => {
    const next = criteriaToLeadQuery(search.criteria)
    patchQuery({ ...next, page: 1 })
    setSearchInput(next.search)
  }

  const streamedIds = useMemo(
    () => new Set(stream.recentLeads.map((lead) => lead.id)),
    [stream.recentLeads],
  )

  const detailQuery = useQuery({
    queryKey: ['property-lead', selectedLeadId],
    queryFn: () => fetchPropertyLeadDetail(selectedLeadId ?? ''),
    enabled: Boolean(selectedLeadId),
  })

  // The row already in hand renders the drawer's frame while the full record loads, so opening
  // a lead never shows an empty panel.
  const preview = useMemo<LeadDetail | null>(() => {
    const row = leads.find((lead) => lead.id === selectedLeadId)
    if (!row) return null
    return {
      ...row,
      description: row.aiSummary,
      images: [row.thumbnail ?? row.image].filter(Boolean) as string[],
      sourcePlatform: row.source,
      metadata: {},
      aiDetails: {
        intent: null,
        confidence: null,
        locationText: row.location,
        price: row.price,
        currency: row.currency,
        areaValue: null,
        areaUnit: null,
        bedrooms: row.bedrooms,
        sellerType: row.sellerType,
      },
    }
  }, [leads, selectedLeadId])

  const selectedLead = detailQuery.data ?? preview

  /** Exports the filtered result set the user is looking at, page by page is not enough. */
  const exportCsv = () => {
    const header = [
      'id', 'title', 'propertyType', 'city', 'location', 'price', 'currency', 'bedrooms',
      'area', 'sellerType', 'score', 'source', 'status', 'dateAdded', 'contactPhone', 'listingUrl',
    ]
    const rows = leads.map((lead) =>
      [
        lead.id, lead.title, lead.propertyType ?? '', lead.city, lead.location, lead.price,
        lead.currency, lead.bedrooms, lead.area, lead.sellerType, lead.score, lead.source,
        lead.status, lead.dateAdded ?? '', lead.contactPhone ?? '', lead.originalListingUrl ?? '',
      ]
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(','),
    )

    const blob = new Blob([[header.join(','), ...rows].join('\n')], {
      type: 'text/csv;charset=utf-8;',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `property_leads_page_${query.page}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const onStatusChange = (status: LeadStatus) => {
    if (!selectedLeadId) return
    setStatus(selectedLeadId, status)
    void detailQuery.refetch()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
        <div>
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Lead management</p>
          <h1 className="text-2xl font-semibold text-white">Property leads</h1>
          <p className="mt-1 text-sm text-slate-400">
            {facets.totalLeads.toLocaleString()} lead(s) on record
            {facets.dateRange.earliest
              ? ` since ${formatDateTime(facets.dateRange.earliest)}`
              : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
            {refreshing ? 'Syncing...' : `${total.toLocaleString()} matching`}
          </span>
          <button
            onClick={exportCsv}
            disabled={leads.length === 0}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10 disabled:opacity-40"
          >
            <Download className="size-4" />
            Export page
          </button>
          <button
            onClick={() => void refresh()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
          >
            <RefreshCcw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <LeadFilterBar
        query={query}
        facets={facets}
        searchInput={searchInput}
        onSearchInput={setSearchInput}
        onPatch={patchQuery}
        onToggle={toggleFilter}
        onReset={reset}
        saveSearch={
          <SaveSearchButton
            query={query}
            saving={savedSearches.create.isPending}
            error={
              savedSearches.create.error instanceof Error
                ? savedSearches.create.error.message
                : null
            }
            onSave={(input) => savedSearches.create.mutateAsync(input)}
          />
        }
      />

      <SavedSearchList
        searches={savedSearches.savedSearches}
        onApply={applySavedSearch}
        onToggle={(search) =>
          savedSearches.update.mutate({ id: search.id, enabled: !search.enabled })
        }
        onDelete={(search) => savedSearches.remove.mutate(search.id)}
      />

      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">
          <AlertTriangle className="size-4" />
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-32" />
          ))}
        </div>
      ) : leads.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-12 text-center">
          <Inbox className="size-8 text-slate-500" />
          <p className="text-slate-300">No leads match these filters.</p>
          <p className="max-w-md text-sm text-slate-500">
            {activeFilterCount(query)
              ? 'Try widening the date range or clearing a filter.'
              : 'Leads appear here as the scanner discovers them.'}
          </p>
          {activeFilterCount(query) ? (
            <button
              onClick={reset}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 hover:bg-white/10"
            >
              Clear all filters
            </button>
          ) : null}
        </div>
      ) : (
        <>
          <LeadList
            leads={leads}
            selectedId={selectedLeadId}
            onSelect={(lead) => setSelectedLeadId(lead.id)}
            highlightIds={streamedIds}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-400">
            <p>
              Showing {range.start.toLocaleString()}-{range.end.toLocaleString()} of{' '}
              {total.toLocaleString()}
            </p>
            <div className="flex items-center gap-2">
              <PageButton label="First" disabled={query.page === 1} onClick={() => setPage(1)} />
              <PageButton
                label="Prev"
                disabled={query.page === 1}
                onClick={() => setPage(Math.max(1, query.page - 1))}
              />
              <span className="px-2 text-slate-300">
                Page {query.page} of {totalPages}
              </span>
              <PageButton
                label="Next"
                disabled={query.page >= totalPages}
                onClick={() => setPage(Math.min(totalPages, query.page + 1))}
              />
              <PageButton
                label="Last"
                disabled={query.page >= totalPages}
                onClick={() => setPage(totalPages)}
              />
            </div>
          </div>
        </>
      )}

      <LeadDrawer
        lead={selectedLead}
        open={Boolean(selectedLeadId)}
        loading={detailQuery.isPending}
        onClose={() => setSelectedLeadId(null)}
        error={detailQuery.error instanceof Error ? detailQuery.error.message : null}
        onStatusChange={onStatusChange}
        statusPending={statusPending}
      />

      <ToastHost
        alerts={stream.recentAlerts}
        onDismiss={stream.dismissAlert}
        onOpenLead={setSelectedLeadId}
      />
    </div>
  )
}

function PageButton({
  label,
  disabled,
  onClick,
}: {
  label: string
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg border border-white/10 px-3 py-1 transition hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {label}
    </button>
  )
}
