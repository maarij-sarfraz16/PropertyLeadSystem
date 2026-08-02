import { LayoutDashboard, LogOut, ShieldCheck, Sparkles } from 'lucide-react'
import { memo } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../lib/auth'
import { GlassCard } from '../components/ui'

const links = [{ to: '/admin', label: 'Overview' }, { to: '/admin/leads', label: 'Leads' }]

export const DashboardLayout = memo(function DashboardLayout() {
  const { user, logout } = useAuth()
  const role = user?.role ?? 'admin'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-3 py-4 lg:flex-row lg:px-6 lg:py-6">
        <aside className="lg:w-72">
          <GlassCard className="p-4 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-2 text-sky-300">
                <Sparkles className="size-5" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Property Radar</p>
                <p className="text-lg font-semibold text-white">{user?.name ?? 'Ops Desk'}</p>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
              <div className="flex items-center gap-2 text-sky-300">
                <ShieldCheck className="size-4" />
                <span className="uppercase tracking-[0.24em]">{role}</span>
              </div>
              <p className="mt-2 text-sm text-slate-400">{user?.email ?? 'ops@propertylead.local'}</p>
            </div>

            <nav className="mt-6 space-y-1">
              {links.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${isActive ? 'bg-sky-500/20 text-sky-100' : 'text-slate-300 hover:bg-white/5 hover:text-white'}`
                  }
                >
                  <LayoutDashboard className="size-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <button
              onClick={logout}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              <LogOut className="size-4" />
              Sign out
            </button>
          </GlassCard>
        </aside>

        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
})
