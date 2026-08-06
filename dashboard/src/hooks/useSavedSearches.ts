import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createSavedSearch,
  deleteSavedSearch,
  fetchSavedSearches,
  updateSavedSearch,
} from '../lib/api'
import type { SavedSearch } from '../types/savedSearches'

export const SAVED_SEARCHES_KEY = ['saved-searches'] as const

/**
 * Saved-search CRUD.
 *
 * Every mutation invalidates the list rather than patching it locally: the server owns
 * derived fields (`unreadCount`, `matchCount`, `lastMatchedAt`) that a local edit cannot
 * compute, and a stale unread badge is exactly the bug this feature exists to avoid.
 */
export function useSavedSearches() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: SAVED_SEARCHES_KEY,
    queryFn: () => fetchSavedSearches(),
    staleTime: 30_000,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: SAVED_SEARCHES_KEY })
  }

  const create = useMutation({
    mutationFn: createSavedSearch,
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ id, ...patch }: { id: string } & Partial<SavedSearch>) =>
      updateSavedSearch(id, patch as Record<string, never>),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSavedSearch(id),
    onSuccess: invalidate,
  })

  return {
    savedSearches: query.data ?? [],
    loading: query.isPending,
    error: query.error instanceof Error ? query.error.message : null,
    refresh: () => query.refetch(),
    create,
    update,
    remove,
  }
}
