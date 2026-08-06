import { useCallback, useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchLeadFacets, fetchLeadPage, updateLeadStatus } from '../lib/api'
import type { LeadStatus } from '../types/dashboard'
import { EMPTY_FACETS, EMPTY_LEAD_QUERY, type LeadQuery } from '../types/leads'

/** Debounce for the search box: one request per pause in typing, not one per keystroke. */
const SEARCH_DEBOUNCE_MS = 300

/**
 * Server-side lead browsing.
 *
 * Filtering, sorting and paging all happen in the backend, so the numbers the page reports
 * ("142 leads match") describe the whole database rather than the slice that happened to be
 * downloaded. `keepPreviousData` holds the current page on screen while the next one loads,
 * which is what stops the table from flashing empty on every filter change.
 */
export function useLeads(initial: Partial<LeadQuery> = {}) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState<LeadQuery>({ ...EMPTY_LEAD_QUERY, ...initial })
  // The value bound to the input; `query.search` is the debounced copy that hits the network.
  const [searchInput, setSearchInput] = useState(query.search)

  useEffect(() => {
    if (searchInput === query.search) return
    const timer = setTimeout(() => {
      setQuery((previous) => ({ ...previous, search: searchInput, page: 1 }))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput, query.search])

  const leadsQuery = useQuery({
    queryKey: ['leads', query],
    queryFn: () => fetchLeadPage(query),
    placeholderData: keepPreviousData,
    // The stream invalidates this key when a lead arrives; the poll is only a dropped-stream
    // safety net.
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  })

  const facetsQuery = useQuery({
    queryKey: ['lead-facets'],
    queryFn: fetchLeadFacets,
    staleTime: 60_000,
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: LeadStatus }) => updateLeadStatus(id, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['leads'] })
      void queryClient.invalidateQueries({ queryKey: ['lead-facets'] })
    },
  })

  /** Any filter change resets to page 1 — page 4 of the old result set means nothing here. */
  const patchQuery = useCallback((patch: Partial<LeadQuery>) => {
    setQuery((previous) => ({
      ...previous,
      ...patch,
      page: patch.page ?? 1,
    }))
  }, [])

  const toggleFilter = useCallback(
    (key: 'cities' | 'sources' | 'sellerTypes' | 'propertyTypes' | 'statuses', value: string) => {
      setQuery((previous) => {
        const current = previous[key]
        const next = current.includes(value)
          ? current.filter((item) => item !== value)
          : [...current, value]
        return { ...previous, [key]: next, page: 1 }
      })
    },
    [],
  )

  const reset = useCallback(() => {
    setSearchInput('')
    setQuery((previous) => ({ ...EMPTY_LEAD_QUERY, pageSize: previous.pageSize, sort: previous.sort }))
  }, [])

  const page = leadsQuery.data
  const range = useMemo(() => {
    if (!page || page.total === 0) return { start: 0, end: 0 }
    const start = (page.page - 1) * page.pageSize + 1
    return { start, end: Math.min(start + page.items.length - 1, page.total) }
  }, [page])

  return {
    query,
    searchInput,
    setSearchInput,
    patchQuery,
    toggleFilter,
    reset,
    setPage: (nextPage: number) => setQuery((previous) => ({ ...previous, page: nextPage })),
    leads: page?.items ?? [],
    total: page?.total ?? 0,
    totalPages: page?.totalPages ?? 1,
    range,
    facets: facetsQuery.data ?? EMPTY_FACETS,
    loading: leadsQuery.isPending,
    refreshing: leadsQuery.isFetching && !leadsQuery.isPending,
    error: leadsQuery.error instanceof Error ? leadsQuery.error.message : null,
    refresh: () => queryClient.invalidateQueries({ queryKey: ['leads'] }),
    setStatus: (id: string, status: LeadStatus) => statusMutation.mutate({ id, status }),
    statusPending: statusMutation.isPending,
  }
}
