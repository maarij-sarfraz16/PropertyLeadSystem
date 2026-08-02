import { Activity, Clock3, RadioTower, Wifi, WifiOff } from 'lucide-react'
import { memo } from 'react'

import type { SourceStatus } from '../types/dashboard'
import { Badge, GlassCard } from './ui'

export const SourceGrid = memo(function SourceGrid({ data }: { data: SourceStatus[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data.map((source) => (
        <GlassCard key={source.name} className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-base font-semibold text-slate-100">{source.name}</p>
            {source.status === 'online' ? (
              <Badge tone="success">
                <span className="inline-flex items-center gap-1">
                  <Wifi className="size-3" /> Online
                </span>
              </Badge>
            ) : (
              <Badge tone="warning">
                <span className="inline-flex items-center gap-1">
                  <WifiOff className="size-3" /> Offline
                </span>
              </Badge>
            )}
          </div>

          <div className="space-y-2 text-sm text-slate-300">
            <p className="flex items-center justify-between"><span className="inline-flex items-center gap-1"><RadioTower className="size-4" /> Leads found</span><span>{source.leadsFound.toLocaleString()}</span></p>
            <p className="flex items-center justify-between"><span className="inline-flex items-center gap-1"><Clock3 className="size-4" /> Last scan</span><span>{source.lastScan}</span></p>
            <p className="flex items-center justify-between"><span className="inline-flex items-center gap-1"><Activity className="size-4" /> Scan frequency</span><span>{source.frequency}</span></p>
          </div>

          <div className="mt-4">
            <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
              <span>Success rate</span>
              <span>{source.successRate}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-linear-to-r from-cyan-400 to-emerald-400" style={{ width: `${source.successRate}%` }} />
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  )
})
