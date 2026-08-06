import { Bell, BellOff, Trash2 } from 'lucide-react'

import { formatRelative } from '../../lib/format'
import type { SavedSearch } from '../../types/savedSearches'
import { describeCriteria } from '../../types/savedSearches'

/**
 * The saved-search rail.
 *
 * Clicking a chip loads its criteria back into the filter bar, which is the payoff of storing
 * criteria in the API's own wire shape: what alerted you and what you are now looking at are
 * the same query, not two implementations that agree by luck.
 *
 * `lastMatchedAt` is shown deliberately — a search that can never match (too narrow, or built
 * on a filter new leads never satisfy) is otherwise invisible, and silence looks identical to
 * "nothing new".
 */
export function SavedSearchList({
  searches,
  onApply,
  onToggle,
  onDelete,
}: {
  searches: SavedSearch[]
  onApply: (search: SavedSearch) => void
  onToggle: (search: SavedSearch) => void
  onDelete: (search: SavedSearch) => void
}) {
  if (searches.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/5 p-3">
      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Saved</span>
      {searches.map((search) => (
        <div
          key={search.id}
          className={`group flex items-center gap-2 rounded-xl border px-3 py-1.5 transition ${
            search.enabled
              ? 'border-white/10 bg-white/5 hover:border-white/20'
              : 'border-white/5 bg-transparent opacity-60'
          }`}
        >
          <button
            type="button"
            onClick={() => onApply(search)}
            className="text-left"
            title={describeCriteria(search.criteria)}
          >
            <span className="flex items-center gap-2 text-sm text-slate-100">
              {search.name}
              {search.unreadCount > 0 ? (
                <span className="rounded-full bg-sky-400/25 px-1.5 text-xs font-semibold text-sky-100">
                  {search.unreadCount}
                </span>
              ) : null}
            </span>
            <span className="block text-[11px] text-slate-500">
              {search.matchCount > 0
                ? `${search.matchCount} matched${
                    formatRelative(search.lastMatchedAt)
                      ? ` · ${formatRelative(search.lastMatchedAt)}`
                      : ''
                  }`
                : 'No matches yet'}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onToggle(search)}
            title={search.enabled ? 'Pause alerts for this search' : 'Resume alerts'}
            className="text-slate-500 transition hover:text-slate-200"
          >
            {search.enabled ? <Bell className="size-3.5" /> : <BellOff className="size-3.5" />}
          </button>
          <button
            type="button"
            onClick={() => onDelete(search)}
            title="Delete this saved search"
            className="text-slate-600 opacity-0 transition hover:text-rose-300 group-hover:opacity-100"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
