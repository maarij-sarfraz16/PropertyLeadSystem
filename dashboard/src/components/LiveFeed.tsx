import {
  Bot,
  CheckCircle2,
  CopyCheck,
  Radar,
  Sparkles,
  UserCheck,
} from 'lucide-react'
import { memo } from 'react'

import type { FeedEvent } from '../types/dashboard'
import { GlassCard } from './ui'

function iconFor(type: FeedEvent['type']) {
  switch (type) {
    case 'new_listing':
      return <Radar className="size-4 text-sky-300" />
    case 'ai_extracted':
      return <Bot className="size-4 text-violet-300" />
    case 'duplicate_detected':
      return <CopyCheck className="size-4 text-amber-300" />
    case 'lead_assigned':
      return <UserCheck className="size-4 text-emerald-300" />
    case 'source_scanned':
      return <CheckCircle2 className="size-4 text-cyan-300" />
    case 'high_score':
      return <Sparkles className="size-4 text-rose-300" />
    default:
      return <Radar className="size-4 text-slate-300" />
  }
}

export const LiveFeed = memo(function LiveFeed({ events }: { events: FeedEvent[] }) {
  return (
    <GlassCard className="p-4">
      <div className="space-y-3">
        {events.map((event) => (
          <div
            key={event.id}
            className="group flex items-start gap-3 rounded-xl border border-white/5 bg-white/3 p-3 transition hover:border-white/15"
          >
            <div className="mt-0.5 rounded-lg bg-white/8 p-2">{iconFor(event.type)}</div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-100 group-hover:text-white">{event.message}</p>
              <p className="mt-1 text-xs text-slate-400">{event.time}</p>
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  )
})
