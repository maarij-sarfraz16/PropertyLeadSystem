import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchDashboardOverview, type DashboardOverview } from '../lib/api'

interface DashboardState {
  data: DashboardOverview
  loading: boolean
  refreshing: boolean
  error: string | null
  isUsingFallback: boolean
  lastUpdated: string
}

const initialState: DashboardState = {
  data: {
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
  },
  loading: true,
  refreshing: false,
  error: null,
  isUsingFallback: false,
  lastUpdated: '—',
}

export function useDashboardData() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: fetchDashboardOverview,
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
    placeholderData: (previousData) => previousData,
  })

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['dashboard-overview'], exact: true })
  }, [queryClient])

  const result = query.data
  const data = result?.data ?? initialState.data

  return {
    data,
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
    error: result?.error ?? (query.error instanceof Error ? query.error.message : null),
    isUsingFallback: result?.isUsingFallback ?? false,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toLocaleTimeString() : '—',
    refresh,
  } satisfies DashboardState & { refresh: () => Promise<void> }
}
