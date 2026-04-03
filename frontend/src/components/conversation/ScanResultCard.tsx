import { useState } from 'react'

interface FolderSummary {
  canonical_path: string
  folder_name: string
  child_count: number
}

interface FileSample {
  filename: string
  canonical_path: string
  extension: string
  size_bytes: number | null
  guessed_category: string | null
}

interface ScanResultPayload {
  scan_id?: string
  scan_depth?: string
  file_count?: number
  folder_count?: number
  file_sample?: FileSample[]
  folder_summaries?: FolderSummary[]
  folders?: FolderSummary[]
  summary?: string
  categories?: Record<string, number>
  changes?: { new_files: number; deleted_files: number }
  file_sample_note?: string
  folders_note?: string
}

interface ScanResultCardProps {
  payload: ScanResultPayload
  onSuggest?: (text: string) => void
}

const DEPTH_LABEL: Record<string, string> = {
  ROOT: 'Root',
  DEEP: 'Deep',
  CONTENT: 'Content (with previews)',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString()
}

export function ScanResultCard({ payload, onSuggest }: ScanResultCardProps) {
  const [showRaw, setShowRaw] = useState(false)

  const depth = payload.scan_depth ?? 'DEEP'
  const depthLabel = DEPTH_LABEL[depth] ?? depth
  const fileCount = payload.file_count ?? payload.file_sample?.length ?? 0
  const folderCount = payload.folder_count ?? 0
  const newFiles = payload.changes?.new_files ?? 0
  const deletedFiles = payload.changes?.deleted_files ?? 0
  const categories = payload.categories ?? {}
  const folders = payload.folder_summaries ?? payload.folders ?? []
  const files = payload.file_sample ?? []

  const topCategories = Object.entries(categories)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)

  const suggestions = [
    'Show the largest files',
    'Show files by category',
    folders.length > 0 ? `Go deeper into ${folders[0]?.folder_name ?? 'first folder'}` : null,
    'Find potential duplicate files',
  ].filter(Boolean) as string[]

  return (
    <div className="tool-card tool-card-scan">
      <div className="tool-card-header">
        <span className="tool-card-icon">🗂</span>
        <span className="tool-card-title">Scan complete</span>
        <span className={`badge badge-depth badge-depth-${depth.toLowerCase()}`}>{depthLabel}</span>
      </div>

      <div className="tool-card-stats">
        <div className="stat">
          <span className="stat-value">{fmt(fileCount)}</span>
          <span className="stat-label">files</span>
        </div>
        <div className="stat">
          <span className="stat-value">{fmt(folderCount)}</span>
          <span className="stat-label">folders</span>
        </div>
        {newFiles > 0 && (
          <div className="stat stat-new">
            <span className="stat-value">+{fmt(newFiles)}</span>
            <span className="stat-label">new</span>
          </div>
        )}
        {deletedFiles > 0 && (
          <div className="stat stat-deleted">
            <span className="stat-value">-{fmt(deletedFiles)}</span>
            <span className="stat-label">removed</span>
          </div>
        )}
      </div>

      {topCategories.length > 0 && (
        <div className="tool-card-categories">
          {topCategories.map(([cat, count]) => (
            <span key={cat} className="category-chip">
              {cat} <span className="category-count">{count}</span>
            </span>
          ))}
        </div>
      )}

      {folders.length > 0 && (
        <div className="tool-card-section">
          <div className="tool-card-section-label">Top folders</div>
          <ul className="folder-list">
            {folders.slice(0, 8).map((f) => (
              <li key={f.canonical_path} className="folder-list-item">
                <span className="folder-name">{f.folder_name}</span>
                {f.child_count > 0 && (
                  <span className="folder-count">{f.child_count} items</span>
                )}
              </li>
            ))}
          </ul>
          {payload.folders_note && (
            <p className="tool-card-note">{payload.folders_note}</p>
          )}
        </div>
      )}

      {files.length > 0 && (
        <div className="tool-card-section">
          <div className="tool-card-section-label">File sample</div>
          <ul className="file-list">
            {files.slice(0, 5).map((f) => (
              <li key={f.canonical_path} className="file-list-item">
                <span className="file-name">{f.filename}</span>
                {f.size_bytes != null && (
                  <span className="file-size">{(f.size_bytes / 1024).toFixed(1)} KB</span>
                )}
              </li>
            ))}
          </ul>
          {payload.file_sample_note && (
            <p className="tool-card-note">{payload.file_sample_note}</p>
          )}
        </div>
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
