import { Outlet } from 'react-router-dom'

import { GlassCard } from '../components/ui'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10 text-slate-100">
      <div className="w-full max-w-5xl">
        <GlassCard className="overflow-hidden">
          <div className="grid min-h-160 grid-cols-1 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.2),transparent_32%),linear-gradient(135deg,rgba(15,23,42,0.95),rgba(30,41,59,0.92))] p-8 md:p-10">
              <p className="text-xs uppercase tracking-[0.32em] text-sky-300">Property Lead Intelligence</p>
              <h1 className="mt-4 text-3xl font-semibold text-white">Command center for live lead ops.</h1>
              <p className="mt-4 max-w-md text-sm leading-7 text-slate-300">
                Monitor fresh listings, review AI extraction confidence, and keep agents focused on the highest-value opportunities.
              </p>
              <div className="mt-8 space-y-3 text-sm text-slate-300">
                <div className="rounded-xl border border-white/10 bg-white/5 p-3">FastAPI-backed live property data with background refresh.</div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3">Open property details without leaving the dashboard.</div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3">Background polling keeps the UI stable while data updates.</div>
              </div>
            </div>
            <div className="flex items-center justify-center p-6 md:p-10">
              <Outlet />
            </div>
          </div>
        </GlassCard>
      </div>
    </div>
  )
}
