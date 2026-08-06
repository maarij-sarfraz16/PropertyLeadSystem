import { BellRing, X } from 'lucide-react'
import { useEffect } from 'react'

import { formatPrice } from '../lib/format'
import type { AlertNotification } from '../types/savedSearches'

const VISIBLE = 3
const DISMISS_AFTER_MS = 8000

/**
 * Transient toasts for saved-search matches.
 *
 * Deliberately capped and self-dismissing: the scanner can discover ~140 leads an hour at
 * peak, and a toast stack that grows without bound is worse than no toast at all. Anything
 * missed here is still in the bell, which is the durable record.
 */
export function ToastHost({
  alerts,
  onDismiss,
  onOpenLead,
}: {
  alerts: AlertNotification[]
  onDismiss: (id: string) => void
  onOpenLead?: (leadId: string) => void
}) {
  const visible = alerts.slice(0, VISIBLE)

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
      {visible.map((alert) => (
        <Toast key={alert.id} alert={alert} onDismiss={onDismiss} onOpenLead={onOpenLead} />
      ))}
    </div>
  )
}

function Toast({
  alert,
  onDismiss,
  onOpenLead,
}: {
  alert: AlertNotification
  onDismiss: (id: string) => void
  onOpenLead?: (leadId: string) => void
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(alert.id), DISMISS_AFTER_MS)
    return () => clearTimeout(timer)
  }, [alert.id, onDismiss])

  return (
    <div className="pointer-events-auto overflow-hidden rounded-xl border border-sky-400/30 bg-slate-900/95 shadow-2xl backdrop-blur-xl">
      <div className="flex items-start gap-2 p-3">
        <BellRing className="mt-0.5 size-4 shrink-0 text-sky-300" />
        <button
          type="button"
          onClick={() => {
            if (alert.leadId) onOpenLead?.(alert.leadId)
            onDismiss(alert.id)
          }}
          className="min-w-0 flex-1 text-left"
        >
          <p className="truncate text-xs text-sky-300">{alert.savedSearchName ?? 'New match'}</p>
          <p className="mt-0.5 truncate text-sm text-slate-100">
            {alert.lead?.title ?? 'A new lead matched'}
          </p>
          {alert.lead ? (
            <p className="mt-0.5 truncate text-xs text-slate-400">
              {formatPrice(alert.lead.price, alert.lead.currency)} · {alert.lead.city} ·{' '}
              {alert.lead.sellerType}
            </p>
          ) : null}
        </button>
        <button
          type="button"
          onClick={() => onDismiss(alert.id)}
          className="shrink-0 text-slate-500 transition hover:text-slate-200"
          aria-label="Dismiss"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  )
}
