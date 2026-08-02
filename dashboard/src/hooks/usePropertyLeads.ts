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
    queryFn: fetchPropertyLeads,
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
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
