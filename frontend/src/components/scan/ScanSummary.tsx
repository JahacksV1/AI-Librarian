interface ScanSummaryProps {
  scanDepth: string
  fileCount: number
  folderCount: number
  newFiles: number
  deletedFiles: number
  categories: Record<string, number>
  topFolders: string[]
}

function folderName(path: string): string {
  return path.split('/').filter(Boolean).pop() ?? path
}

export function ScanSummary({
  scanDepth,
  fileCount,
  folderCount,
  newFiles,
  deletedFiles,
  categories,
  topFolders,
}: ScanSummaryProps) {
  const sortedCategories = Object.entries(categories).sort(([, a], [, b]) => b - a)
  const isRoot = scanDepth === 'ROOT'

  return (
    <div className="scan-summary">
      {isRoot ? (
        // ROOT view: show folder tree at the top level
        <>
          <div className="scan-counts">
            <span className="scan-stat">{folderCount > 0 ? folderCount - 1 : 0} folders</span>
            {fileCount > 0 && (
              <>
                <span className="scan-stat-sep">/</span>
                <span className="scan-stat">{fileCount} files at root</span>
              </>
            )}
          </div>

          {topFolders.length > 0 && (
            <ul className="scan-folder-list">
              {topFolders.map((path) => (
                <li key={path} className="scan-folder-item">
                  <span className="scan-folder-icon">📁</span>
                  <span className="scan-folder-name">{folderName(path)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        // DEEP / CONTENT view: file + folder counts, changes, categories
        <>
          <div className="scan-counts">
            <span className="scan-stat">{fileCount} files</span>
            <span className="scan-stat-sep">/</span>
            <span className="scan-stat">{folderCount} folders</span>
          </div>

          {(newFiles > 0 || deletedFiles > 0) && (
            <div className="scan-changes">
              {newFiles > 0 && <span className="scan-change new">+{newFiles} new</span>}
              {deletedFiles > 0 && <span className="scan-change deleted">−{deletedFiles} removed</span>}
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
        </>
      )}
    </div>
  )
}
