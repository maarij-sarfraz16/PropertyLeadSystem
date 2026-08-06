import { CalendarRange, RotateCcw, Search, SlidersHorizontal } from 'lucide-react'

import type { LeadFacets, LeadQuery, LeadSort } from '../../types/leads'
import { DATE_PRESET_LABELS, SORT_LABELS, activeFilterCount, type DatePreset } from '../../types/leads'
import { FilterSelect } from './FilterSelect'

const DATE_PRESETS: DatePreset[] = ['all', 'today', 'yesterday', 'last7', 'last30', 'custom']

/** Score bands, phrased the way the scoring panel labels them. */
const SCORE_BANDS: Array<{ label: string; min: number | null; max: number | null }> = [
  { label: 'Any score', min: null, max: null },
  { label: 'Hot (85+)', min: 85, max: null },
  { label: 'High (70-84)', min: 70, max: 84 },
  { label: 'Medium (40-69)', min: 40, max: 69 },
  { label: 'Low (<40)', min: null, max: 39 },
]

function scoreBandKey(query: LeadQuery) {
  const match = SCORE_BANDS.find((band) => band.min === query.minScore && band.max === query.maxScore)
  return match?.label ?? 'Any score'
}

export function LeadFilterBar({
  query,
  facets,
  searchInput,
  onSearchInput,
  onPatch,
  onToggle,
  onReset,
  saveSearch,
}: {
  query: LeadQuery
  facets: LeadFacets
  searchInput: string
  onSearchInput: (value: string) => void
  onPatch: (patch: Partial<LeadQuery>) => void
  onToggle: (
    key: 'cities' | 'sources' | 'sellerTypes' | 'propertyTypes' | 'statuses',
    value: string,
  ) => void
  onReset: () => void
  /** Rendered next to Clear. Injected rather than imported so this stays a pure filter bar. */
  saveSearch?: React.ReactNode
}) {
  const activeCount = activeFilterCount(query)

  return (
    <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="relative w-full xl:max-w-lg">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input
            value={searchInput}
            onChange={(event) => onSearchInput(event.target.value)}
            placeholder="Search title, location, city, contact..."
            className="w-full rounded-xl border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/50 focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={query.sort}
            onChange={(event) => onPatch({ sort: event.target.value as LeadSort })}
            className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200"
          >
            {(Object.keys(SORT_LABELS) as LeadSort[]).map((sort) => (
              <option key={sort} value={sort}>
                {SORT_LABELS[sort]}
              </option>
            ))}
          </select>

          <select
            value={query.pageSize}
            onChange={(event) => onPatch({ pageSize: Number(event.target.value) })}
            className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200"
          >
            {[10, 25, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size} per page
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={onReset}
            disabled={activeCount === 0}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-white/10 disabled:opacity-40"
          >
            <RotateCcw className="size-3.5" />
            Clear{activeCount ? ` (${activeCount})` : ''}
          </button>

          {saveSearch}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
        <SlidersHorizontal className="size-4 text-slate-400" />
        <FilterSelect
          label="City"
          options={facets.cities}
          selected={query.cities}
          onToggle={(value) => onToggle('cities', value)}
          onClear={() => onPatch({ cities: [] })}
        />
        <FilterSelect
          label="Source"
          options={facets.sources}
          selected={query.sources}
          onToggle={(value) => onToggle('sources', value)}
          onClear={() => onPatch({ sources: [] })}
        />
        <FilterSelect
          label="Property type"
          options={facets.propertyTypes}
          selected={query.propertyTypes}
          onToggle={(value) => onToggle('propertyTypes', value)}
          onClear={() => onPatch({ propertyTypes: [] })}
        />
        <FilterSelect
          label="Seller"
          options={facets.sellerTypes}
          selected={query.sellerTypes}
          onToggle={(value) => onToggle('sellerTypes', value)}
          onClear={() => onPatch({ sellerTypes: [] })}
        />
        <FilterSelect
          label="Status"
          options={facets.statuses}
          selected={query.statuses}
          onToggle={(value) => onToggle('statuses', value)}
          onClear={() => onPatch({ statuses: [] })}
        />

        <select
          value={scoreBandKey(query)}
          onChange={(event) => {
            const band = SCORE_BANDS.find((item) => item.label === event.target.value)
            onPatch({ minScore: band?.min ?? null, maxScore: band?.max ?? null })
          }}
          className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200"
        >
          {SCORE_BANDS.map((band) => (
            <option key={band.label} value={band.label}>
              {band.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
        <CalendarRange className="size-4 text-slate-400" />
        {DATE_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => onPatch({ datePreset: preset })}
            className={`rounded-lg border px-3 py-1.5 text-sm transition ${
              query.datePreset === preset
                ? 'border-sky-400/40 bg-sky-500/15 text-sky-100'
                : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'
            }`}
          >
            {DATE_PRESET_LABELS[preset]}
          </button>
        ))}

        {query.datePreset === 'custom' ? (
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-300">
            <input
              type="date"
              value={query.customFrom}
              max={query.customTo || undefined}
              onChange={(event) => onPatch({ customFrom: event.target.value })}
              className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-slate-200 [color-scheme:dark]"
            />
            <span className="text-slate-500">to</span>
            <input
              type="date"
              value={query.customTo}
              min={query.customFrom || undefined}
              onChange={(event) => onPatch({ customTo: event.target.value })}
              className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-slate-200 [color-scheme:dark]"
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}
