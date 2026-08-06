import { Check, ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

/**
 * Multi-select dropdown for one filter facet.
 *
 * Options come from the backend facets endpoint, so every value offered here is one that
 * actually exists in the database — a dropdown built from the current page could not offer
 * the city the user is looking for unless a lead from it happened to be on screen.
 */
export function FilterSelect({
  label,
  options,
  selected,
  onToggle,
  onClear,
}: {
  label: string
  options: string[]
  selected: string[]
  onToggle: (value: string) => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const active = selected.length > 0

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        disabled={options.length === 0}
        className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
          active
            ? 'border-sky-400/40 bg-sky-500/15 text-sky-100'
            : 'border-white/10 bg-white/5 text-slate-200 hover:bg-white/10'
        }`}
      >
        {label}
        {active ? (
          <span className="rounded-full bg-sky-400/25 px-1.5 text-xs font-semibold">{selected.length}</span>
        ) : null}
        <ChevronDown className={`size-3.5 transition ${open ? 'rotate-180' : ''}`} />
      </button>

      {open ? (
        <div className="absolute left-0 z-30 mt-1 max-h-72 w-56 overflow-y-auto rounded-xl border border-white/10 bg-slate-900/95 p-1 shadow-xl backdrop-blur-xl">
          {active ? (
            <button
              type="button"
              onClick={onClear}
              className="mb-1 w-full rounded-lg px-3 py-1.5 text-left text-xs uppercase tracking-wide text-slate-400 hover:bg-white/5 hover:text-slate-200"
            >
              Clear {label.toLowerCase()}
            </button>
          ) : null}
          {options.map((option) => {
            const checked = selected.includes(option)
            return (
              <button
                key={option}
                type="button"
                onClick={() => onToggle(option)}
                className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-1.5 text-left text-sm text-slate-200 hover:bg-white/5"
              >
                <span className="truncate capitalize">{option}</span>
                {checked ? <Check className="size-3.5 shrink-0 text-sky-300" /> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
