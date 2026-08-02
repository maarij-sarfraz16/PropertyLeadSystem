import { Flame, GaugeCircle, ShieldAlert, ShieldCheck } from 'lucide-react'
import { memo } from 'react'

import { Badge, GlassCard } from './ui'

function scoreTone(score: number): 'critical' | 'warning' | 'info' | 'success' {
  if (score >= 95) return 'critical'
  if (score >= 90) return 'success'
  if (score >= 80) return 'info'
  return 'warning'
}

function scoreIcon(score: number) {
  if (score >= 95) return <Flame className="size-4 text-rose-300" />
  if (score >= 90) return <ShieldCheck className="size-4 text-emerald-300" />
  if (score >= 80) return <GaugeCircle className="size-4 text-sky-300" />
  return <ShieldAlert className="size-4 text-amber-300" />
}

export const ScoringPanel = memo(function ScoringPanel({ rows }: { rows: Array<{ id: string; score: number; label: string; city: string; area: string }> }) {
  if (!rows.length) {
    return <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No scoring data available.</p>
  }

  return (
    <GlassCard className="p-4">
      <div className="space-y-3">
        {rows.map((item) => (
          <div key={item.id} className="rounded-xl border border-white/10 bg-white/3 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-slate-100">
                {scoreIcon(item.score)}
                <p className="font-medium">{item.city}</p>
                <p className="text-slate-500">{item.area}</p>
              </div>
              <Badge tone={scoreTone(item.score)}>{item.label}</Badge>
            </div>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
              <span>Lead Score</span>
              <span>{item.score}/100</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-linear-to-r from-sky-400 via-violet-400 to-rose-400"
                style={{ width: `${item.score}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  )
})
