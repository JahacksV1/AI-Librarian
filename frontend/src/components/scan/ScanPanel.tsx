import type { ScanState } from '../../hooks/useScan'
import { ScanSummary } from './ScanSummary'

interface ScanPanelProps {
  scan: ScanState
}

const DEPTH_LABEL: Record<string, string> = {
  ROOT: 'Root',
  DEEP: 'Deep',
  CONTENT: 'Content',
}

export function ScanPanel({ scan }: ScanPanelProps) {
  if (scan.status === 'idle') return null

  const depthLabel = scan.scanDepth ? (DEPTH_LABEL[scan.scanDepth] ?? scan.scanDepth) : null
  const rootName = scan.rootPath ? scan.rootPath.split('/').filter(Boolean).pop() ?? scan.rootPath : null

  return (
    <div className="scan-panel">
      <div className="panel-header">
        <div className="scan-header-left">
          <h2>Scan Results</h2>
          {rootName && <span className="scan-root-path">{rootName}</span>}
        </div>
        <div className="scan-header-badges">
          {depthLabel && (
            <span className={`badge badge-depth badge-depth-${(scan.scanDepth ?? 'deep').toLowerCase()}`}>
              {depthLabel}
            </span>
          )}
          <span className={`badge badge-${scan.status}`}>
            {scan.status === 'scanning' ? 'Scanning…' : scan.status === 'complete' ? 'Complete' : 'Failed'}
          </span>
        </div>
      </div>

      {scan.status === 'scanning' && (
        <div className="scan-progress">
          <div className="scan-spinner" />
          <span>
            {scan.scanDepth === 'ROOT'
              ? `Mapping ${scan.rootPath ?? 'folder'}…`
              : scan.scanDepth === 'CONTENT'
                ? `Reading files in ${scan.rootPath ?? 'folder'}…`
                : `Scanning ${scan.rootPath ?? 'files'}…`}
          </span>
        </div>
      )}

      {scan.status === 'complete' && (
        <ScanSummary
          scanDepth={scan.scanDepth ?? 'DEEP'}
          fileCount={scan.fileCount}
          folderCount={scan.folderCount}
          newFiles={scan.newFiles}
          deletedFiles={scan.deletedFiles}
          categories={scan.categories}
          topFolders={scan.topFolders}
        />
      )}

      {scan.status === 'failed' && (
        <p className="panel-error">Scan failed. Check the activity log for details.</p>
      )}
    </div>
  )
}
