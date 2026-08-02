import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { memo } from 'react'

import type { AnalyticsData } from '../types/dashboard'
import { GlassCard } from './ui'

const COLORS = ['#38bdf8', '#8b5cf6', '#f97316', '#34d399', '#facc15', '#fb7185']

export const AnalyticsPanel = memo(function AnalyticsPanel({ analytics }: { analytics: AnalyticsData }) {
  const hasData = Object.values(analytics).some((value) => Array.isArray(value) && value.length > 0)

  if (!hasData) {
    return <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">No analytics data available.</p>
  }

  const { dailyLeads, cityLeads, sourceLeads, intentMix, sellerMix, priceDistribution, conversion } = analytics

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Leads Per Day</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={dailyLeads}>
              <CartesianGrid stroke="rgba(148,163,184,0.15)" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="leads" stroke="#38bdf8" strokeWidth={3} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Leads Per City</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={cityLeads}>
              <CartesianGrid stroke="rgba(148,163,184,0.15)" strokeDasharray="3 3" />
              <XAxis dataKey="city" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="leads" radius={[8, 8, 0, 0]} isAnimationActive={false}>
                {cityLeads.map((_, i) => (
                  <Cell key={`city-${i}`} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Leads Per Source</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sourceLeads}>
              <CartesianGrid stroke="rgba(148,163,184,0.15)" strokeDasharray="3 3" />
              <XAxis dataKey="source" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="leads" fill="#818cf8" radius={[8, 8, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Buy vs Rent vs Sell</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip />
              <Pie data={intentMix} dataKey="value" nameKey="name" outerRadius={80} innerRadius={52} isAnimationActive={false}>
                {intentMix.map((_, i) => (
                  <Cell key={`intent-${i}`} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Owner vs Agent Listings</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip />
              <Pie data={sellerMix} dataKey="value" nameKey="name" outerRadius={84} innerRadius={44} isAnimationActive={false}>
                {sellerMix.map((_, i) => (
                  <Cell key={`seller-${i}`} fill={COLORS[(i + 2) % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Price Distribution</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={priceDistribution}>
              <CartesianGrid stroke="rgba(148,163,184,0.15)" strokeDasharray="3 3" />
              <XAxis dataKey="band" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#22d3ee" radius={[8, 8, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-4 xl:col-span-2">
        <h3 className="mb-3 text-sm font-semibold text-slate-200">Conversion Analytics</h3>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={conversion}>
              <CartesianGrid stroke="rgba(148,163,184,0.15)" strokeDasharray="3 3" />
              <XAxis dataKey="stage" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#34d399" strokeWidth={3} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>
    </div>
  )
})
