import { BrainCircuit } from 'lucide-react'
import { memo } from 'react'

import { GlassCard } from './ui'

export const InsightsPanel = memo(function InsightsPanel({ insights }: { insights: string[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {insights.map((insight) => (
        <GlassCard key={insight} className="p-4">
          <div className="mb-2 inline-flex rounded-lg bg-violet-500/20 p-2">
            <BrainCircuit className="size-4 text-violet-300" />
          </div>
          <p className="text-sm text-slate-200">{insight}</p>
        </GlassCard>
      ))}
    </div>
  )
})
