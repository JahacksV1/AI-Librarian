interface ScanSummaryProps {
  fileCount: number
  folderCount: number
  newFiles: number
  deletedFiles: number
  categories: Record<string, number>
}

export function ScanSummary({ fileCount, folderCount, newFiles, deletedFiles, categories }: ScanSummaryProps) {
  const sortedCategories = Object.entries(categories).sort(([, a], [, b]) => b - a)

  return (
    <div className="scan-summary">
      <div className="scan-counts">
        <span className="scan-stat">{fileCount} files</span>
        <span className="scan-stat-sep">/</span>
        <span className="scan-stat">{folderCount} folders</span>
      </div>

      {(newFiles > 0 || deletedFiles > 0) && (
        <div className="scan-changes">
          {newFiles > 0 && <span className="scan-change new">+{newFiles} new</span>}
          {deletedFiles > 0 && <span className="scan-change deleted">-{deletedFiles} removed</span>}
        </div>
      )}

      {sortedCategories.length > 0 && (
        <div className="scan-categories">
          {sortedCategories.map(([cat, count]) => (
            <span key={cat} className="scan-cat-tag">
              {cat} <span className="scan-cat-count">{count}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
