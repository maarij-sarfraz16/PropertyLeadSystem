import { motion } from 'framer-motion'
import { BellRing, Bot, Database, Radar, Sparkles, UserRoundCheck } from 'lucide-react'
import { memo } from 'react'

import { GlassCard } from './ui'

const steps = [
  { label: 'Scraping', icon: Radar },
  { label: 'AI Extraction', icon: Bot },
  { label: 'Deduplication', icon: Database },
  { label: 'Lead Scoring', icon: Sparkles },
  { label: 'Notifications', icon: BellRing },
  { label: 'Agent Assignment', icon: UserRoundCheck },
]

export const PipelineViz = memo(function PipelineViz({ stages }: { stages: Array<{ label: string; status: string }> }) {
  if (!stages.length) {
    return <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No pipeline data available.</p>
  }

  return (
    <GlassCard className="p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stages.map((stage, i) => {
          const step = steps.find((item) => item.label === stage.label) ?? steps[i % steps.length]
          const Icon = step.icon
          return (
            <motion.div
              key={stage.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.35 }}
              className="relative rounded-xl border border-white/10 bg-white/3 p-3 text-center"
            >
              <div className="mx-auto mb-2 inline-flex rounded-lg bg-white/8 p-2">
                <Icon className="size-4 text-sky-300" />
              </div>
              <p className="text-sm text-slate-200">{stage.label}</p>
              <p className="mt-1 text-xs uppercase tracking-[0.24em] text-slate-400">{stage.status}</p>
              {i !== stages.length - 1 ? (
                <div className="pointer-events-none absolute -right-2 top-1/2 hidden h-px w-4 -translate-y-1/2 bg-sky-300/40 xl:block" />
              ) : null}
            </motion.div>
          )
        })}
      </div>
    </GlassCard>
  )
})
