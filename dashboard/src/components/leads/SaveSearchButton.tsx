import { BellPlus, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { previewCriteria } from '../../lib/api'
import type { LeadQuery } from '../../types/leads'
import { activeFilterCount } from '../../types/leads'
import { isMatchable, leadQueryToCriteria, type SearchPreview } from '../../types/savedSearches'

/**
 * Turns the current filter state into a standing alert.
 *
 * Two things make this more than a name prompt. The button is disabled while no filter is
 * active, mirroring the server's rule that a search must narrow something — so the user never
 * submits a request that is guaranteed to 422. And the popover previews how many existing
 * leads the criteria match, which is the honest answer to "how noisy will this be?" and the
 * real defence against a search that buries the inbox.
 */
export function SaveSearchButton({
  query,
  onSave,
  saving,
  error,
}: {
  query: LeadQuery
  onSave: (input: { name: string; criteria: Record<string, unknown>; notifyRealtime: boolean }) => Promise<unknown>
  saving: boolean
  error: string | null
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [notifyRealtime, setNotifyRealtime] = useState(true)
  const [preview, setPreview] = useState<SearchPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const criteria = leadQueryToCriteria(query)
  const canSave = activeFilterCount(query) > 0 && isMatchable(criteria)

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

  // Preview when the popover opens, so the count reflects the filters actually in effect.
  useEffect(() => {
    if (!open) {
      setPreview(null)
      return
    }
    let cancelled = false
    setPreviewing(true)
    previewCriteria(criteria)
      .then((result) => {
        if (!cancelled) setPreview(result)
      })
      .catch(() => {
        if (!cancelled) setPreview(null)
      })
      .finally(() => {
        if (!cancelled) setPreviewing(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const submit = async () => {
    if (!name.trim()) return
    await onSave({ name: name.trim(), criteria, notifyRealtime })
    setName('')
    setOpen(false)
  }

  const noisy = preview?.estimatedPerDay != null && preview.estimatedPerDay > 50

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        disabled={!canSave}
        title={
          canSave
            ? 'Save these filters and get alerted when new leads match'
            : 'Add at least one filter before saving a search'
        }
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <BellPlus className="size-3.5" />
        Save search
      </button>

      {open ? (
        <div className="absolute right-0 z-40 mt-1 w-80 rounded-xl border border-white/10 bg-slate-900/95 p-3 shadow-xl backdrop-blur-xl">
          <p className="text-sm font-medium text-slate-100">Alert me about these filters</p>

          <p className="mt-2 text-xs text-slate-400">
            {previewing ? (
              <span className="inline-flex items-center gap-1.5">
                <Loader2 className="size-3 animate-spin" /> Checking how many leads match...
              </span>
            ) : preview ? (
              <>
                Matches{' '}
                <span className="font-semibold text-slate-200">
                  {preview.total.toLocaleString()}
                </span>{' '}
                existing lead(s)
                {preview.estimatedPerDay != null ? (
                  <>
                    {' '}· roughly{' '}
                    <span className={noisy ? 'font-semibold text-amber-300' : 'text-slate-300'}>
                      {preview.estimatedPerDay}/day
                    </span>
                  </>
                ) : null}
                {noisy ? (
                  <span className="mt-1 block text-amber-300/90">
                    That is a lot of alerts — consider narrowing it.
                  </span>
                ) : null}
              </>
            ) : (
              'Could not preview the match count.'
            )}
          </p>

          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit()
            }}
            placeholder="Name, e.g. Owner plots in DHA"
            className="mt-3 w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/50 focus:outline-none"
          />

          <label className="mt-2 flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={notifyRealtime}
              onChange={(event) => setNotifyRealtime(event.target.checked)}
              className="size-3.5 accent-sky-500"
            />
            Pop up a toast the moment one matches
          </label>

          {query.datePreset !== 'all' ? (
            <p className="mt-2 rounded-lg bg-white/5 px-2 py-1.5 text-[11px] text-slate-400">
              The date range is not saved — a standing alert always watches new leads.
            </p>
          ) : null}

          {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}

          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg px-2.5 py-1.5 text-sm text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!name.trim() || saving}
              className="inline-flex items-center gap-1.5 rounded-lg border border-sky-400/40 bg-sky-500/15 px-3 py-1.5 text-sm text-sky-100 transition hover:bg-sky-500/25 disabled:opacity-40"
            >
              {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Save
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
