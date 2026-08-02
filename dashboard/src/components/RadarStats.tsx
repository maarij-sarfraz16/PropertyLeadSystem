import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { memo } from 'react'

import type { Metric } from '../types/dashboard'
import { AnimatedNumber, FadeIn, GlassCard } from './ui'

function TrendIcon({ trend }: { trend: Metric['trend'] }) {
  if (trend === 'up') return <ArrowUpRight className="size-4 text-emerald-300" />
  if (trend === 'down') return <ArrowDownRight className="size-4 text-rose-300" />
  return <Minus className="size-4 text-slate-300" />
}

export const RadarStats = memo(function RadarStats({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric, idx) => (
        <FadeIn key={metric.label} delay={idx * 0.04}>
          <GlassCard className="p-4">
            <p className="text-xs uppercase tracking-[0.16em] text-slate-400">{metric.label}</p>
            <div className="mt-2 flex items-end justify-between gap-2">
              <p className="text-2xl font-semibold text-white">
                <AnimatedNumber value={metric.value} suffix={metric.suffix} />
              </p>
              <div className="flex items-center gap-1 rounded-full bg-white/6 px-2 py-1 text-xs text-slate-300">
                <TrendIcon trend={metric.trend} />
                <span>{metric.change}</span>
              </div>
            </div>
          </GlassCard>
        </FadeIn>
      ))}
    </div>
  )
})
