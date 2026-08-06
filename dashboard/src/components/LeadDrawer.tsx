import { AnimatePresence, motion } from 'framer-motion'
import {
  ChevronLeft,
  ChevronRight,
  CircleX,
  Clock,
  ExternalLink,
  ImageOff,
  Phone,
  Sparkles,
  User,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import type { LeadDetail, LeadStatus } from '../types/dashboard'
import { formatDateTime, formatPriceExact, formatRelative, scoreLabel, scoreTone } from '../lib/format'
import { Badge, SkeletonBlock } from './ui'

const STATUSES: LeadStatus[] = ['new', 'reviewed', 'assigned', 'archived']

/**
 * Full record for one lead.
 *
 * Everything the backend returned is rendered — including the raw provider payload — because
 * the operator reviewing a lead is the person who needs to spot that, say, the extracted price
 * disagrees with the listing. Hiding fields we did not anticipate would hide exactly that.
 */
export function LeadDrawer({
  lead,
  open,
  onClose,
  error,
  loading,
  onStatusChange,
  statusPending,
}: {
  lead: LeadDetail | null
  open: boolean
  onClose: () => void
  error?: string | null
  loading?: boolean
  onStatusChange?: (status: LeadStatus) => void
  statusPending?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && lead ? (
        <>
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            aria-label="Close lead details"
            className="fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'tween', duration: 0.25 }}
            className="fixed right-0 top-0 z-50 h-full w-full max-w-2xl overflow-y-auto border-l border-white/10 bg-slate-950/95 p-5 backdrop-blur-2xl"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <Badge tone={scoreTone(lead.score)}>
                    Score {lead.score} · {scoreLabel(lead.score)}
                  </Badge>
                  <Badge>{lead.sourcePlatform ?? lead.source}</Badge>
                  <Badge>{lead.propertyType ?? 'Unknown type'}</Badge>
                </div>
                <p className="text-lg font-semibold text-white">{lead.title}</p>
                <p className="text-sm text-slate-400">
                  {lead.city} — {lead.location}
                </p>
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="rounded-lg border border-white/10 p-2 text-slate-300 hover:text-white"
              >
                <CircleX className="size-4" />
              </button>
            </div>

            {error ? (
              <p className="mb-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">
                {error}
              </p>
            ) : null}

            <Gallery images={lead.images} fallback={lead.thumbnail ?? lead.image} title={lead.title} />

            {onStatusChange ? (
              <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-white/3 p-3">
                <span className="text-xs uppercase tracking-wide text-slate-400">Status</span>
                {STATUSES.map((status) => (
                  <button
                    key={status}
                    type="button"
                    disabled={statusPending}
                    onClick={() => onStatusChange(status)}
                    className={`rounded-lg border px-3 py-1 text-sm capitalize transition disabled:opacity-50 ${
                      lead.status === status
                        ? 'border-sky-400/40 bg-sky-500/15 text-sky-100'
                        : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            ) : null}

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <Stat label="Price" value={formatPriceExact(lead.price, lead.currency)} />
              <Stat label="Area" value={lead.area || 'Unknown'} />
              <Stat label="Bedrooms" value={lead.bedrooms ? String(lead.bedrooms) : 'Unknown'} />
              <Stat label="Seller type" value={lead.sellerType} />
              <Stat label="City" value={lead.city} />
              <Stat label="Property type" value={lead.propertyType ?? 'Unknown'} />
            </div>

            <Section title="Description">
              {loading ? (
                <SkeletonBlock className="h-16" />
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-300">
                  {lead.description || lead.aiSummary || 'No description captured.'}
                </p>
              )}
            </Section>

            <Section title="Contact" icon={<User className="size-4 text-sky-300" />}>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Row label="Name" value={lead.contactName ?? 'Not published'} />
                <Row
                  label="Phone"
                  value={lead.contactPhone ?? 'Not published'}
                  href={lead.contactPhone ? `tel:${lead.contactPhone}` : undefined}
                  icon={lead.contactPhone ? <Phone className="size-3" /> : undefined}
                />
              </div>
            </Section>

            <Section title="AI extraction" icon={<Sparkles className="size-4 text-violet-300" />}>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Row label="Intent" value={lead.aiDetails.intent ?? 'Unknown'} />
                <Row
                  label="Confidence"
                  value={
                    lead.aiDetails.confidence != null
                      ? `${Math.round(lead.aiDetails.confidence * 100)}%`
                      : 'Unknown'
                  }
                />
                <Row label="Location text" value={lead.aiDetails.locationText ?? lead.location} />
                <Row
                  label="Extracted price"
                  value={
                    lead.aiDetails.price != null
                      ? formatPriceExact(lead.aiDetails.price, lead.aiDetails.currency ?? lead.currency)
                      : 'Not extracted'
                  }
                />
                <Row
                  label="Extracted area"
                  value={
                    lead.aiDetails.areaValue != null
                      ? `${lead.aiDetails.areaValue} ${lead.aiDetails.areaUnit ?? ''}`.trim()
                      : 'Not extracted'
                  }
                />
                <Row label="Seller type" value={lead.aiDetails.sellerType ?? 'Unknown'} />
              </div>
            </Section>

            <Section title="Provenance" icon={<Clock className="size-4 text-slate-300" />}>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Row label="Source platform" value={lead.sourcePlatform ?? lead.source} />
                <Row
                  label="Date added"
                  value={`${formatDateTime(lead.dateAdded)}${formatRelative(lead.dateAdded) ? ` (${formatRelative(lead.dateAdded)})` : ''}`}
                />
                <Row label="Scraped at" value={formatDateTime(lead.scrapedAt)} />
                <Row label="Posted on platform" value={formatDateTime(lead.postedAt)} />
                <Row label="Last seen" value={formatDateTime(lead.lastSeen)} />
                <Row label="Lead id" value={lead.id} />
              </div>
              {lead.originalListingUrl ? (
                <a
                  className="mt-3 inline-flex items-center gap-1 text-sm text-sky-300 hover:text-sky-200"
                  href={lead.originalListingUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open original listing <ExternalLink className="size-3" />
                </a>
              ) : (
                <p className="mt-3 text-sm text-slate-500">
                  No verified listing URL was captured for this lead.
                </p>
              )}
            </Section>

            <Section title="Raw listing metadata">
              {Object.keys(lead.metadata ?? {}).length ? (
                <details className="group">
                  <summary className="cursor-pointer text-sm text-slate-400 hover:text-slate-200">
                    {Object.keys(lead.metadata).length} field(s) returned by the source
                  </summary>
                  <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-900/70 p-3 text-xs leading-6 text-slate-300">
                    {JSON.stringify(lead.metadata, null, 2)}
                  </pre>
                </details>
              ) : (
                <p className="text-sm text-slate-500">No additional metadata was returned.</p>
              )}
            </Section>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  )
}

/** Gallery with a primary image and a thumbnail strip; keyboard arrows move between shots. */
function Gallery({
  images,
  fallback,
  title,
}: {
  images: string[]
  fallback?: string | null
  title: string
}) {
  const gallery = images.length ? images : fallback ? [fallback] : []
  const [index, setIndex] = useState(0)
  // Identifies "a different set of photos", so switching leads starts the gallery at the first
  // image rather than at whatever position the previous lead was left on.
  const galleryKey = `${gallery.length}:${gallery[0] ?? ''}`

  useEffect(() => {
    setIndex(0)
  }, [galleryKey])

  if (!gallery.length) {
    return (
      <div className="flex h-56 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/3 text-sm text-slate-500">
        <ImageOff className="size-5" /> No images available
      </div>
    )
  }

  const step = (delta: number) => setIndex((current) => (current + delta + gallery.length) % gallery.length)

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white/3">
      <div className="relative">
        <img src={gallery[index]} alt={title} className="h-64 w-full object-cover" />
        {gallery.length > 1 ? (
          <>
            <GalleryButton side="left" onClick={() => step(-1)} />
            <GalleryButton side="right" onClick={() => step(1)} />
            <span className="absolute bottom-2 right-2 rounded-full bg-slate-950/80 px-2 py-0.5 text-xs text-slate-200">
              {index + 1} / {gallery.length}
            </span>
          </>
        ) : null}
      </div>

      {gallery.length > 1 ? (
        <div className="flex gap-2 overflow-x-auto p-2">
          {gallery.map((image, position) => (
            <button
              key={`${image}-${position}`}
              type="button"
              onClick={() => setIndex(position)}
              className={`size-16 shrink-0 overflow-hidden rounded-lg border transition ${
                position === index ? 'border-sky-400' : 'border-white/10 hover:border-white/30'
              }`}
            >
              <img src={image} alt="" loading="lazy" className="size-full object-cover" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function GalleryButton({ side, onClick }: { side: 'left' | 'right'; onClick: () => void }) {
  const Icon = side === 'left' ? ChevronLeft : ChevronRight
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={side === 'left' ? 'Previous image' : 'Next image'}
      className={`absolute top-1/2 -translate-y-1/2 rounded-full bg-slate-950/70 p-2 text-slate-200 transition hover:bg-slate-950 ${
        side === 'left' ? 'left-2' : 'right-2'
      }`}
    >
      <Icon className="size-4" />
    </button>
  )
}

function Section({
  title,
  icon,
  children,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="mt-4 rounded-xl border border-white/10 bg-white/3 p-4">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <p className="text-sm font-medium text-slate-200">{title}</p>
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/3 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium capitalize text-slate-100">{value}</p>
    </div>
  )
}

function Row({
  label,
  value,
  href,
  icon,
}: {
  label: string
  value: string
  href?: string
  icon?: React.ReactNode
}) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      {href ? (
        <a href={href} className="inline-flex items-center gap-1 text-sm text-sky-300 hover:text-sky-200">
          {icon}
          {value}
        </a>
      ) : (
        <p className="wrap-break-word text-sm text-slate-200">{value}</p>
      )}
    </div>
  )
}
