import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchPropertyLeads } from '../lib/api'
import type { LeadRow } from '../types/dashboard'

interface PropertyLeadState {
  data: LeadRow[]
  loading: boolean
  refreshing: boolean
  error: string | null
  lastUpdated: string
}

export function usePropertyLeads() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['property-leads'],
    // Wrapped, not passed by reference: react-query calls queryFn with a context object, which
    // would otherwise arrive as the `limit` argument.
    queryFn: () => fetchPropertyLeads(),
    // New leads arrive over the WebSocket (see useLeadStream), so this poll is only a safety
    // net for a dropped stream — not the update mechanism. A 5s poll here would issue ~700
    // needless requests an hour per open tab.
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    placeholderData: (previousData) => previousData,
  })

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['property-leads'], exact: true })
  }, [queryClient])

  return {
    data: query.data ?? [],
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
    error: query.error instanceof Error ? query.error.message : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toLocaleTimeString() : '—',
    refresh,
  } satisfies PropertyLeadState & { refresh: () => Promise<void> }
}
