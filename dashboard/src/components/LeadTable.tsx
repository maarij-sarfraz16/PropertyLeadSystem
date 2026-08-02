import { Download, Search, SlidersHorizontal } from 'lucide-react'
import { memo } from 'react'
import { useMemo, useState } from 'react'

import type { LeadRow } from '../types/dashboard'
import { Badge, GlassCard } from './ui'

type SortBy = 'score' | 'price' | 'lastSeen'

const PAGE_SIZE = 4

function parseDateValue(value?: string | null) {
  if (!value) return 0
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) {
    return 0
  }
  return parsed
}

function formatDateLabel(value?: string | null) {
  if (!value) return 'Unknown'
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(parsed)
}

export const LeadTable = memo(function LeadTable({
  leads,
  onRowClick,
}: {
  leads: LeadRow[]
  onRowClick: (lead: LeadRow) => void
}) {
  const [query, setQuery] = useState('')
  const [city, setCity] = useState('all')
  const [seller, setSeller] = useState('all')
  const [propertyType, setPropertyType] = useState('all')
  const [sortBy, setSortBy] = useState<SortBy>('score')
  const [page, setPage] = useState(1)

  const cities = useMemo(() => ['all', ...new Set(leads.map((l) => l.city))], [leads])
  const propertyTypes = useMemo(() => ['all', ...new Set(leads.map((l) => l.propertyType).filter(Boolean) as string[])], [leads])

  const filtered = useMemo(() => {
    let next = leads.filter((lead) => {
      const q = query.toLowerCase()
      const matchesQuery =
        lead.title.toLowerCase().includes(q) ||
        lead.location.toLowerCase().includes(q) ||
        lead.source.toLowerCase().includes(q) ||
        (lead.propertyType ?? '').toLowerCase().includes(q)
      const matchesCity = city === 'all' || lead.city === city
      const matchesSeller = seller === 'all' || lead.sellerType === seller
      const matchesPropertyType = propertyType === 'all' || lead.propertyType === propertyType
      return matchesQuery && matchesCity && matchesSeller && matchesPropertyType
    })

    next = [...next].sort((a, b) => {
      if (sortBy === 'score') return b.score - a.score
      if (sortBy === 'price') return b.price - a.price
      return parseDateValue(b.dateAdded ?? b.lastSeen) - parseDateValue(a.dateAdded ?? a.lastSeen)
    })

    return next
  }, [leads, query, city, seller, propertyType, sortBy])

  const maxPage = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const exportCsv = () => {
    const header = ['id', 'title', 'propertyType', 'city', 'location', 'price', 'bedrooms', 'area', 'sellerType', 'score', 'source', 'status', 'dateAdded']
    const lines = filtered.map((lead) =>
      [
        lead.id,
        lead.title,
        lead.propertyType ?? '',
        lead.city,
        lead.location,
        lead.price,
        lead.bedrooms,
        lead.area,
        lead.sellerType,
        lead.score,
        lead.source,
        lead.status,
        lead.dateAdded ?? lead.lastSeen,
      ]
        .map((v) => `"${String(v).replaceAll('"', '""')}"`)
        .join(','),
    )

    const csv = [header.join(','), ...lines].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'property_leads.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <GlassCard className="p-4">
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPage(1)
            }}
            placeholder="Search by title, location, source..."
            className="w-full rounded-xl border border-white/10 bg-white/4 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/50 focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SlidersHorizontal className="size-4 text-slate-400" />
          <select value={city} onChange={(e) => setCity(e.target.value)} className="rounded-lg border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-200">
            {cities.map((c) => (
              <option key={c} value={c}>{c === 'all' ? 'All Cities' : c}</option>
            ))}
          </select>
          <select value={propertyType} onChange={(e) => setPropertyType(e.target.value)} className="rounded-lg border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-200">
            {propertyTypes.map((type) => (
              <option key={type} value={type}>{type === 'all' ? 'All Types' : type}</option>
            ))}
          </select>
          <select value={seller} onChange={(e) => setSeller(e.target.value)} className="rounded-lg border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-200">
            <option value="all">All Sellers</option>
            <option value="owner">Owner</option>
            <option value="agent">Agent</option>
            <option value="unknown">Unknown</option>
          </select>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)} className="rounded-lg border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-200">
            <option value="score">Sort: Score</option>
            <option value="price">Sort: Price</option>
            <option value="lastSeen">Sort: Date Added</option>
          </select>
          <button onClick={exportCsv} className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-100 hover:bg-white/10">
            <Download className="size-4" /> Export
          </button>
        </div>
      </div>

      <div className="overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2">Property</th>
              <th className="px-3 py-2">City</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">Beds</th>
              <th className="px-3 py-2">Area</th>
              <th className="px-3 py-2">Seller</th>
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Date Added</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((lead) => (
              <tr
                key={lead.id}
                onClick={() => onRowClick(lead)}
                className="cursor-pointer border-t border-white/5 text-slate-200 transition hover:bg-white/4"
              >
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    {lead.thumbnail || lead.image ? <img src={lead.thumbnail ?? lead.image ?? undefined} alt={lead.title} className="h-10 w-14 rounded object-cover" /> : null}
                    <div>
                      <p className="font-medium">{lead.title}</p>
                      <p className="text-xs text-slate-400">{lead.location}</p>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-3">{lead.city}</td>
                <td className="px-3 py-3 text-slate-300">{lead.propertyType ?? 'Unknown'}</td>
                <td className="px-3 py-3">{lead.price.toLocaleString()} PKR</td>
                <td className="px-3 py-3">{lead.bedrooms}</td>
                <td className="px-3 py-3">{lead.area}</td>
                <td className="px-3 py-3">{lead.sellerType}</td>
                <td className="px-3 py-3">
                  <Badge tone={lead.score > 90 ? 'critical' : lead.score > 80 ? 'info' : 'warning'}>
                    {lead.score}
                  </Badge>
                </td>
                <td className="px-3 py-3">{lead.source}</td>
                <td className="px-3 py-3 text-slate-400">{formatDateLabel(lead.dateAdded ?? lead.lastSeen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
        <p>
          Showing {pageRows.length} of {filtered.length} leads
        </p>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-lg border border-white/10 px-3 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <span>
            {page}/{maxPage}
          </span>
          <button
            disabled={page === maxPage}
            onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
            className="rounded-lg border border-white/10 px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </GlassCard>
  )
})
