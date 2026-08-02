import { Bell, CircleAlert, CircleCheck, Info } from 'lucide-react'
import { memo } from 'react'

import type { NotificationItem } from '../types/dashboard'
import { Badge, GlassCard } from './ui'

function iconFor(level: NotificationItem['level']) {
  switch (level) {
    case 'critical':
      return <CircleAlert className="size-4 text-rose-300" />
    case 'warning':
      return <CircleAlert className="size-4 text-amber-300" />
    case 'success':
      return <CircleCheck className="size-4 text-emerald-300" />
    default:
      return <Info className="size-4 text-sky-300" />
  }
}

function toneFor(level: NotificationItem['level']) {
  if (level === 'critical') return 'critical'
  if (level === 'warning') return 'warning'
  if (level === 'success') return 'success'
  return 'info'
}

export const NotificationCenter = memo(function NotificationCenter({ items }: { items: NotificationItem[] }) {
  return (
    <GlassCard className="p-4">
      <div className="mb-3 flex items-center gap-2 text-slate-200">
        <Bell className="size-4" />
        <p className="font-medium">Notification Center</p>
      </div>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-xl border border-white/10 bg-white/3 p-3">
            <div className="mb-1 flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
                {iconFor(item.level)}
                {item.title}
              </div>
              <Badge tone={toneFor(item.level) as 'critical' | 'warning' | 'success' | 'info'}>
                {item.level}
              </Badge>
            </div>
            <p className="text-sm text-slate-300">{item.body}</p>
            <p className="mt-1 text-xs text-slate-500">{item.time}</p>
          </div>
        ))}
      </div>
    </GlassCard>
  )
})
