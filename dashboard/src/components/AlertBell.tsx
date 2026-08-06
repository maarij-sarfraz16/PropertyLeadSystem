import { Bell, Check, Inbox } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useAlerts } from '../hooks/useAlerts'
import { formatPrice, formatRelative } from '../lib/format'
import type { AlertNotification } from '../types/savedSearches'

/**
 * The alert inbox, reachable from anywhere in the dashboard.
 *
 * Reads from REST rather than from the realtime stream: the stream drops events for a lagging
 * client by design, so the bell must not depend on having received every push. The stream
 * only invalidates these queries to make the update immediate.
 */
export function AlertBell({ onOpenLead }: { onOpenLead?: (leadId: string) => void }) {
  const { alerts, unreadCount, markRead, markAllRead } = useAlerts()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const openAlert = (alert: AlertNotification) => {
    if (!alert.readAt) markRead.mutate(alert.id)
    if (alert.leadId) onOpenLead?.(alert.leadId)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        title="Saved-search alerts"
        className="relative inline-flex size-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-300 transition hover:bg-white/10"
      >
        <Bell className="size-4" />
        {unreadCount > 0 ? (
          <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-sky-500 px-1 text-[10px] font-semibold leading-4 text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-96 overflow-hidden rounded-xl border border-white/10 bg-slate-900/95 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-white/5 px-3 py-2">
            <p className="text-sm font-medium text-slate-100">
              Alerts{unreadCount > 0 ? ` · ${unreadCount} unread` : ''}
            </p>
            {unreadCount > 0 ? (
              <button
                type="button"
                onClick={() => markAllRead.mutate(undefined)}
                className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
              >
                <Check className="size-3" />
                Mark all read
              </button>
            ) : null}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                <Inbox className="size-6 text-slate-600" />
                <p className="text-sm text-slate-400">No alerts yet.</p>
                <p className="max-w-[16rem] text-xs text-slate-500">
                  Filter the leads list, then "Save search" to be told when new inventory
                  matches.
                </p>
              </div>
            ) : (
              alerts.map((alert) => (
                <button
                  key={alert.id}
                  type="button"
                  onClick={() => openAlert(alert)}
                  className={`flex w-full gap-3 border-b border-white/5 px-3 py-2.5 text-left transition hover:bg-white/5 ${
                    alert.readAt ? 'opacity-60' : ''
                  }`}
                >
                  <span
                    className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                      alert.readAt ? 'bg-transparent' : 'bg-sky-400'
                    }`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs text-sky-300">
                      {alert.savedSearchName ?? 'Alert'}
                    </span>
                    {alert.body ? (
                      <span className="mt-0.5 block text-xs text-amber-200/90">{alert.body}</span>
                    ) : (
                      <>
                        <span className="mt-0.5 block truncate text-sm text-slate-100">
                          {alert.lead?.title ?? 'Lead'}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-slate-400">
                          {alert.lead
                            ? `${formatPrice(alert.lead.price, alert.lead.currency)} · ${
                                alert.lead.city
                              } · ${alert.lead.sellerType}`
                            : ''}
                        </span>
                      </>
                    )}
                    <span className="mt-0.5 block text-[11px] text-slate-500">
                      {formatRelative(alert.createdAt) ?? ''}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
