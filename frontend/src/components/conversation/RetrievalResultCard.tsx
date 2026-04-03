import { useState } from 'react'

interface RetrievalResult {
  canonical_path?: string
  filename?: string
  folder_name?: string
  extension?: string
  size_bytes?: number | null
  guessed_category?: string | null
  modified_at?: string | null
}

interface RetrievalCounts {
  total_files?: number
  total_size_bytes?: number
  by_category?: Record<string, number>
  by_extension?: Record<string, number>
  total_folders?: number
}

interface RetrievalPayload {
  entity_type?: string
  total_matching?: number
  returned?: number
  results?: RetrievalResult[]
  counts?: RetrievalCounts
}

interface QueryArgs {
  path_prefix?: string
  entity_type?: string
  extension?: string
  category?: string
  sort_by?: string
  sort_order?: string
  limit?: number
  include_counts?: boolean
}

interface RetrievalResultCardProps {
  payload: RetrievalPayload
  args?: QueryArgs
  onSuggest?: (text: string) => void
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString()
}

function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function RetrievalResultCard({ payload, args, onSuggest }: RetrievalResultCardProps) {
  const [showRaw, setShowRaw] = useState(false)

  const entityType = payload.entity_type ?? args?.entity_type ?? 'file'
  const totalMatching = payload.total_matching ?? 0
  const returned = payload.returned ?? payload.results?.length ?? 0
  const results = payload.results ?? []
  const counts = payload.counts

  // Build a readable description of what was queried
  const queryParts: string[] = []
  if (args?.extension) queryParts.push(`.${args.extension.replace(/^\./, '')} files`)
  else if (entityType === 'folder') queryParts.push('folders')
  else queryParts.push('files')
  if (args?.category) queryParts.push(`in category "${args.category}"`)
  if (args?.path_prefix) queryParts.push(`under ${args.path_prefix.split('/').filter(Boolean).slice(-2).join('/')}`)
  if (args?.sort_by) queryParts.push(`sorted by ${args.sort_by} ${args.sort_order ?? 'asc'}`)
  const queryDesc = queryParts.join(' ')

  const suggestions = [
    totalMatching > returned ? `Show more results (${totalMatching - returned} remaining)` : null,
    args?.extension ? `Find duplicates among these ${args.extension} files` : null,
    entityType === 'file' ? 'Show category breakdown for these results' : null,
    args?.path_prefix ? `Scan deeper into ${args.path_prefix.split('/').pop()}` : null,
  ].filter(Boolean) as string[]

  return (
    <div className="tool-card tool-card-retrieval">
      <div className="tool-card-header">
        <span className="tool-card-icon">🔍</span>
        <span className="tool-card-title">Retrieval: {queryDesc}</span>
      </div>

      <div className="tool-card-stats">
        <div className="stat">
          <span className="stat-value">{fmt(totalMatching)}</span>
          <span className="stat-label">matching</span>
        </div>
        <div className="stat">
          <span className="stat-value">{fmt(returned)}</span>
          <span className="stat-label">shown</span>
        </div>
        {counts?.total_size_bytes != null && (
          <div className="stat">
            <span className="stat-value">{fmtBytes(counts.total_size_bytes)}</span>
            <span className="stat-label">total size</span>
          </div>
        )}
      </div>

      {counts?.by_category && Object.keys(counts.by_category).length > 0 && (
        <div className="tool-card-categories">
          {Object.entries(counts.by_category)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 6)
            .map(([cat, count]) => (
              <span key={cat} className="category-chip">
                {cat} <span className="category-count">{count}</span>
              </span>
            ))}
        </div>
      )}

      {results.length > 0 && (
        <div className="tool-card-section">
          <ul className="file-list">
            {results.slice(0, 8).map((r, i) => (
              <li key={r.canonical_path ?? i} className="file-list-item">
                <span className="file-name">{r.filename ?? r.folder_name ?? r.canonical_path}</span>
                {r.size_bytes != null && (
                  <span className="file-size">{fmtBytes(r.size_bytes)}</span>
                )}
              </li>
            ))}
          </ul>
          {totalMatching > returned && (
            <p className="tool-card-note">
              Showing {returned} of {totalMatching} — use a higher limit or more specific filters to narrow results.
            </p>
          )}
        </div>
      )}

      {results.length === 0 && (
        <p className="tool-card-empty">No results found for this query.</p>
      )}

      {onSuggest && suggestions.length > 0 && (
        <div className="tool-card-suggestions">
          <span className="tool-card-section-label">Follow-up</span>
          <div className="suggestion-chips">
            {suggestions.map((s) => (
              <button
                key={s}
                className="suggestion-chip"
                onClick={() => onSuggest(s)}
                type="button"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        className="tool-card-raw-toggle"
        type="button"
        onClick={() => setShowRaw((v) => !v)}
      >
        {showRaw ? 'Hide raw data' : 'Show raw data'}
      </button>
      {showRaw && (
        <pre className="tool-card-raw">{JSON.stringify(payload, null, 2)}</pre>
      )}
    </div>
  )
}
