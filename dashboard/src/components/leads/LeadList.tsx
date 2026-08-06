import { Building2, ExternalLink, ImageOff, MapPin } from 'lucide-react'
import { memo, useState } from 'react'

import type { LeadRow } from '../../types/dashboard'
import { formatDateTime, formatPrice, formatPriceExact, formatRelative, scoreLabel, scoreTone } from '../../lib/format'
import { Badge } from '../ui'

const STATUS_TONE: Record<string, 'default' | 'success' | 'warning' | 'info'> = {
  new: 'info',
  incomplete: 'warning',
  reviewed: 'success',
  assigned: 'warning',
  archived: 'default',
}

/**
 * The lead list itself.
 *
 * Rows are whole records rather than a grid of cells: an operator scanning this list is asking
 * "is this lead worth opening", and that judgement needs the photo, the price and the score
 * adjacent, not spread across eleven columns they have to scroll sideways to read.
 */
/** Thumbnail that degrades to a placeholder when the origin blocks or drops the image. */
function Thumbnail({ src, alt }: { src?: string | null; alt: string }) {
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div className="flex size-full items-center justify-center text-slate-600">
        <ImageOff className="size-6" />
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className="size-full object-cover"
      onError={() => setFailed(true)}
    />
  )
}

export const LeadList = memo(function LeadList({
  leads,
  selectedId,
  onSelect,
  highlightIds,
}: {
  leads: LeadRow[]
  selectedId: string | null
  onSelect: (lead: LeadRow) => void
  /** Leads pushed over the realtime stream this session; briefly marked as new arrivals. */
  highlightIds?: ReadonlySet<string>
}) {
  return (
    <ul className="space-y-2">
      {leads.map((lead) => {
        const thumbnail = lead.thumbnail ?? lead.image
        const isSelected = lead.id === selectedId
        return (
          <li key={lead.id}>
            <button
              type="button"
              onClick={() => onSelect(lead)}
              aria-current={isSelected}
              className={`flex w-full gap-4 rounded-2xl border p-3 text-left transition ${
                isSelected
                  ? 'border-sky-400/50 bg-sky-500/10'
                  : highlightIds?.has(lead.id)
                    ? 'border-emerald-400/30 bg-emerald-500/8 hover:bg-emerald-500/12'
                    : 'border-white/10 bg-white/4 hover:border-white/20 hover:bg-white/8'
              }`}
            >
              <div className="relative size-24 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-slate-900 sm:size-28">
                <Thumbnail src={thumbnail} alt="" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-100">{lead.title}</p>
                    <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-slate-400">
                      <MapPin className="size-3 shrink-0" />
                      {lead.location}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {highlightIds?.has(lead.id) ? (
                      <Badge tone="success">New</Badge>
                    ) : null}
                    <Badge tone={scoreTone(lead.score)}>
                      {lead.score} · {scoreLabel(lead.score)}
                    </Badge>
                  </div>
                </div>

                <p
                  className="mt-2 text-lg font-semibold text-white"
                  title={formatPriceExact(lead.price, lead.currency)}
                >
                  {formatPrice(lead.price, lead.currency)}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                  <span className="inline-flex items-center gap-1 text-slate-300">
                    <Building2 className="size-3" />
                    {lead.propertyType ?? 'Unknown type'}
                  </span>
                  <Meta label="City" value={lead.city} />
                  <Meta label="Area" value={lead.area} />
                  {lead.bedrooms ? <Meta label="Beds" value={String(lead.bedrooms)} /> : null}
                  <Meta label="Seller" value={lead.sellerType} />
                  <Meta label="Source" value={lead.source} />
                </div>

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="text-slate-500" title={formatDateTime(lead.dateAdded)}>
                    Added {formatDateTime(lead.dateAdded)}
                    {formatRelative(lead.dateAdded) ? ` · ${formatRelative(lead.dateAdded)}` : ''}
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge tone={STATUS_TONE[lead.status] ?? 'default'}>{lead.status}</Badge>
                    {lead.originalListingUrl ? (
                      <a
                        href={lead.originalListingUrl}
                        target="_blank"
                        rel="noreferrer"
                        // The row opens the detail view; the link must not also trigger it.
                        onClick={(event) => event.stopPropagation()}
                        className="inline-flex items-center gap-1 text-sky-300 hover:text-sky-200"
                      >
                        Listing <ExternalLink className="size-3" />
                      </a>
                    ) : (
                      <span
                        className="text-slate-600"
                        title="No verified listing URL was captured for this lead."
                      >
                        No link
                      </span>
                    )}
                  </span>
                </div>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
})

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-slate-500">{label}:</span>{' '}
      <span className="capitalize text-slate-300">{value || 'Unknown'}</span>
    </span>
  )
}
