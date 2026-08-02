import { motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { clsx } from 'clsx'

export function GlassCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={clsx(
        'rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_20px_60px_-20px_rgba(14,165,233,0.35)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function SectionTitle({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-white md:text-xl">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-slate-400">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  )
}

export function Badge({
  children,
  tone = 'default',
}: {
  children: ReactNode
  tone?: 'default' | 'success' | 'warning' | 'critical' | 'info'
}) {
  const map: Record<string, string> = {
    default: 'bg-white/10 text-slate-200 border-white/10',
    success: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25',
    warning: 'bg-amber-500/15 text-amber-300 border-amber-400/25',
    critical: 'bg-rose-500/15 text-rose-300 border-rose-400/25',
    info: 'bg-sky-500/15 text-sky-300 border-sky-400/25',
  }

  return (
    <span className={clsx('rounded-full border px-2 py-1 text-xs font-medium', map[tone])}>
      {children}
    </span>
  )
}

export function AnimatedNumber({
  value,
  suffix,
}: {
  value: number
  suffix?: string
}) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const duration = 900
    const start = performance.now()

    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      setDisplay(Math.round(value * progress))
      if (progress < 1) {
        requestAnimationFrame(tick)
      }
    }

    requestAnimationFrame(tick)
  }, [value])

  const formatted = useMemo(() => {
    if (value > 1000000) return display.toLocaleString('en-US')
    if (value % 1 !== 0) return display.toFixed(1)
    return display.toLocaleString('en-US')
  }, [display, value])

  return (
    <span>
      {formatted}
      {suffix ?? ''}
    </span>
  )
}

export function FadeIn({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}

export function SkeletonBlock({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-xl bg-white/8', className)} />
}
