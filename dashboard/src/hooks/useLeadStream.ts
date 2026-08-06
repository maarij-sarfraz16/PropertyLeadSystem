import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { normalizeLeadRow, streamUrls } from '../lib/api'
import type { LeadRow } from '../types/dashboard'
import type { AlertNotification } from '../types/savedSearches'

export type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'offline'

export interface StreamEvent {
  type: string
  ts: string
  data: Record<string, unknown>
}

interface UseLeadStreamResult {
  status: StreamStatus
  /** Leads pushed since mount, newest first. Drives the "new lead" highlight. */
  recentLeads: LeadRow[]
  lastEventAt: string | null
  newLeadCount: number
  clearNewLeads: () => void
  /** Saved-search alerts pushed since mount, newest first. Drives the toast stack. */
  recentAlerts: AlertNotification[]
  dismissAlert: (id: string) => void
}

/** Backoff schedule for reconnects: quick at first, then back off to avoid hammering a
 *  backend that is genuinely down. Capped so a recovered backend is picked up promptly. */
const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000, 15000]
const MAX_RECENT_LEADS = 25
const MAX_RECENT_ALERTS = 25

/**
 * Live connection to the backend event stream.
 *
 * Transport: WebSocket first; if it fails to establish twice in a row we fall back to SSE,
 * which survives proxies that refuse to upgrade connections. Both carry identical events, so
 * the handling below is transport-agnostic.
 *
 * On `lead.created` the new row is written straight into the react-query cache, so it appears
 * without waiting for a refetch. Aggregate data (metrics, charts) cannot be derived from a
 * single lead, so `dashboard.updated` invalidates that query instead — one refetch per scan
 * cycle that actually produced leads, rather than a fixed poll.
 */
export function useLeadStream(): UseLeadStreamResult {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [recentLeads, setRecentLeads] = useState<LeadRow[]>([])
  const [lastEventAt, setLastEventAt] = useState<string | null>(null)
  const [newLeadCount, setNewLeadCount] = useState(0)
  const [recentAlerts, setRecentAlerts] = useState<AlertNotification[]>([])

  // Refs, not state: these are connection bookkeeping and must not trigger re-renders (which
  // would tear down and rebuild the very connection they describe).
  const socketRef = useRef<WebSocket | null>(null)
  const sourceRef = useRef<EventSource | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const wsFailuresRef = useRef(0)
  const closedRef = useRef(false)

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      if (event.type === 'heartbeat') return
      setLastEventAt(event.ts)

      if (event.type === 'lead.created') {
        const lead = normalizeLeadRow(event.data?.lead as Partial<LeadRow> | undefined)
        if (!lead.id) return

        // Prepend to the cached list so the table updates instantly. Guarding on id keeps a
        // reconnect replay or a duplicate delivery from showing the same lead twice.
        queryClient.setQueryData<LeadRow[]>(['property-leads'], (previous) => {
          const rows = previous ?? []
          if (rows.some((row) => row.id === lead.id)) return rows
          return [lead, ...rows]
        })

        // The Leads workspace pages server-side, so a new row cannot simply be spliced into a
        // cached page — where it belongs depends on the active filters and sort. Refetching
        // the current page is the only way to keep it consistent with `total`.
        void queryClient.invalidateQueries({ queryKey: ['leads'] })
        void queryClient.invalidateQueries({ queryKey: ['lead-facets'] })

        setRecentLeads((previous) =>
          previous.some((row) => row.id === lead.id)
            ? previous
            : [lead, ...previous].slice(0, MAX_RECENT_LEADS),
        )
        setNewLeadCount((count) => count + 1)
        return
      }

      if (event.type === 'alert.created') {
        const alert = event.data?.alert as AlertNotification | undefined
        if (!alert?.id) return

        // The inbox is the source of truth, so refetch it rather than splicing: the badge
        // count and read state live server-side. `alert.created` is published after the
        // `lead.created` for the same lead, so the lead is already cached by the time the
        // toast renders and can be opened straight from it.
        void queryClient.invalidateQueries({ queryKey: ['notifications'] })
        void queryClient.invalidateQueries({ queryKey: ['alert-unread-count'] })

        setRecentAlerts((previous) =>
          previous.some((item) => item.id === alert.id)
            ? previous
            : [alert, ...previous].slice(0, MAX_RECENT_ALERTS),
        )
        return
      }

      if (event.type === 'dashboard.updated') {
        void queryClient.invalidateQueries({ queryKey: ['dashboard-overview'], exact: true })
      }
    },
    [queryClient],
  )

  useEffect(() => {
    closedRef.current = false

    const scheduleReconnect = () => {
      if (closedRef.current) return
      const delay = RECONNECT_DELAYS_MS[Math.min(attemptRef.current, RECONNECT_DELAYS_MS.length - 1)]
      attemptRef.current += 1
      setStatus(attemptRef.current > 1 ? 'offline' : 'reconnecting')
      timerRef.current = setTimeout(connect, delay)
    }

    const parse = (raw: string) => {
      try {
        handleEvent(JSON.parse(raw) as StreamEvent)
      } catch {
        // A malformed frame is not worth dropping a healthy connection over.
      }
    }

    const connectSse = () => {
      const source = new EventSource(streamUrls().sse)
      sourceRef.current = source
      source.onopen = () => {
        attemptRef.current = 0
        setStatus('live')
      }
      source.onmessage = (message) => parse(message.data)
      source.onerror = () => {
        source.close()
        sourceRef.current = null
        scheduleReconnect()
      }
    }

    function connect() {
      if (closedRef.current) return

      // Two failed WebSocket attempts is a strong signal the path is blocked rather than the
      // server being briefly down, so stop retrying it and use SSE from here on.
      if (wsFailuresRef.current >= 2) {
        connectSse()
        return
      }

      let opened = false
      try {
        const socket = new WebSocket(streamUrls().ws)
        socketRef.current = socket

        socket.onopen = () => {
          opened = true
          wsFailuresRef.current = 0
          attemptRef.current = 0
          setStatus('live')
        }
        socket.onmessage = (message) => parse(message.data)
        socket.onerror = () => {
          if (!opened) wsFailuresRef.current += 1
        }
        socket.onclose = () => {
          if (!opened) wsFailuresRef.current += 1
          socketRef.current = null
          scheduleReconnect()
        }
      } catch {
        wsFailuresRef.current += 1
        scheduleReconnect()
      }
    }

    connect()

    return () => {
      // Tear everything down on unmount. Without this, a route change would leave the socket
      // open and its handlers holding the old component's closures — a real memory leak.
      closedRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
      socketRef.current?.close()
      sourceRef.current?.close()
      socketRef.current = null
      sourceRef.current = null
    }
  }, [handleEvent])

  const clearNewLeads = useCallback(() => setNewLeadCount(0), [])

  const dismissAlert = useCallback((id: string) => {
    setRecentAlerts((previous) => previous.filter((alert) => alert.id !== id))
  }, [])

  return {
    status,
    recentLeads,
    lastEventAt,
    newLeadCount,
    clearNewLeads,
    recentAlerts,
    dismissAlert,
  }
}
