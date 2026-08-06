import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '../lib/api'

export const NOTIFICATIONS_KEY = ['notifications'] as const
export const UNREAD_COUNT_KEY = ['alert-unread-count'] as const

/**
 * The alert inbox.
 *
 * Polls on an interval *as well as* listening to the realtime stream. That is deliberate
 * rather than redundant: the broker drops events for a lagging subscriber by design, so a
 * client that was backgrounded during a burst would otherwise show a permanently stale
 * badge. The poll is the floor; the stream is the fast path.
 */
export function useAlerts() {
  const queryClient = useQueryClient()

  const notifications = useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => fetchNotifications({ limit: 50 }),
    refetchInterval: 120_000,
  })

  const unread = useQuery({
    queryKey: UNREAD_COUNT_KEY,
    queryFn: fetchUnreadCount,
    refetchInterval: 120_000,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY })
    void queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY })
  }

  const markRead = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: invalidate,
  })

  const markAllRead = useMutation({
    mutationFn: (savedSearchId?: string) => markAllNotificationsRead(savedSearchId),
    onSuccess: invalidate,
  })

  return {
    alerts: notifications.data ?? [],
    loading: notifications.isPending,
    error: notifications.error instanceof Error ? notifications.error.message : null,
    unreadCount: unread.data?.count ?? 0,
    unreadBySearch: unread.data?.bySearch ?? {},
    markRead,
    markAllRead,
    refresh: invalidate,
  }
}
