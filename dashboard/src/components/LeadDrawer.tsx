import { AnimatePresence, motion } from 'framer-motion'
import { CircleX, ExternalLink, Sparkles } from 'lucide-react'

import type { LeadDetail } from '../types/dashboard'

export function LeadDrawer({
  lead,
  open,
  onClose,
  error,
}: {
  lead: LeadDetail | null
  open: boolean
  onClose: () => void
  error?: string | null
}) {
  return (
    <AnimatePresence>
      {open && lead ? (
        <>
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-slate-950/65"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'tween', duration: 0.25 }}
            className="fixed right-0 top-0 z-50 h-full w-full max-w-xl overflow-y-auto border-l border-white/10 bg-slate-950/90 p-5 backdrop-blur-2xl"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <p className="text-lg font-semibold text-white">{lead.title}</p>
                <p className="text-sm text-slate-400">
                  {lead.city} - {lead.location}
                </p>
              </div>
              <button onClick={onClose} className="rounded-lg border border-white/10 p-2 text-slate-300 hover:text-white">
                <CircleX className="size-4" />
              </button>
            </div>

            {error ? <p className="mb-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</p> : null}

            <div className="mb-4 overflow-hidden rounded-xl border border-white/10 bg-white/3">
              {lead.images.length ? (
                <div className="grid grid-cols-1 gap-2 p-2 sm:grid-cols-2">
                  {lead.images.slice(0, 4).map((image) => (
                    <img key={image} src={image} alt={lead.title} className="h-40 w-full rounded-lg object-cover" />
                  ))}
                </div>
              ) : lead.thumbnail || lead.image ? (
                <img src={lead.thumbnail ?? lead.image ?? undefined} alt={lead.title} className="h-52 w-full object-cover" />
              ) : (
                <div className="flex h-52 items-center justify-center text-sm text-slate-500">No images available</div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <Stat label="Price" value={`${lead.price.toLocaleString()} PKR`} />
              <Stat label="Bedrooms" value={String(lead.bedrooms)} />
              <Stat label="Area" value={lead.area} />
              <Stat label="Property Type" value={lead.propertyType ?? 'Unknown'} />
              <Stat label="Seller" value={lead.sellerType} />
              <Stat label="Source" value={lead.source} />
              <Stat label="Date Added" value={lead.dateAdded ?? lead.lastSeen} />
              <Stat label="Scraped At" value={lead.scrapedAt ?? 'Unknown'} />
            </div>

            <div className="mt-4 rounded-xl border border-white/10 bg-white/3 p-4">
              <div className="mb-2 flex items-center gap-2 text-slate-200">
                <Sparkles className="size-4 text-violet-300" />
                <p className="font-medium">AI Summary</p>
              </div>
              <p className="text-sm text-slate-300">{lead.description ?? lead.aiSummary}</p>
            </div>

            <div className="mt-4 space-y-3 rounded-xl border border-white/10 bg-white/3 p-4">
              <Row label="Lead Score" value={`${lead.score}/100`} />
              <Row label="Source Platform" value={lead.sourcePlatform ?? lead.source} />
              <Row label="Contact Name" value={lead.contactName ?? 'Unavailable'} />
              <Row label="Contact Phone" value={lead.contactPhone ?? 'Unavailable'} />
              <Row label="AI Intent" value={lead.aiDetails.intent ?? 'Unknown'} />
              <Row label="AI Confidence" value={lead.aiDetails.confidence != null ? `${Math.round(lead.aiDetails.confidence * 100)}%` : 'Unknown'} />
              <Row label="AI Location" value={lead.aiDetails.locationText ?? lead.location} />
              <Row label="Original Listing" value={lead.originalListingUrl ? 'Available' : 'Unavailable'} />
              {lead.originalListingUrl ? (
                <a className="inline-flex items-center gap-1 text-sm text-sky-300 hover:text-sky-200" href={lead.originalListingUrl} target="_blank" rel="noreferrer">
                  Open listing <ExternalLink className="size-3" />
                </a>
              ) : null}
            </div>

            <div className="mt-4 rounded-xl border border-white/10 bg-white/3 p-4">
              <p className="mb-2 text-sm font-medium text-slate-200">Additional Metadata</p>
              <pre className="overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-300">
                {JSON.stringify(lead.metadata, null, 2)}
              </pre>
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/3 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-100">{value}</p>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm text-slate-200">{value}</p>
    </div>
  )
}
