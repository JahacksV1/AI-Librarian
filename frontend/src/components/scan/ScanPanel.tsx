import type { ScanState } from '../../hooks/useScan'
import { ScanSummary } from './ScanSummary'

interface ScanPanelProps {
  scan: ScanState
}

export function ScanPanel({ scan }: ScanPanelProps) {
  if (scan.status === 'idle') return null

  return (
    <div className="scan-panel">
      <div className="panel-header">
        <h2>Scan Results</h2>
        <span className={`badge badge-${scan.status}`}>
          {scan.status === 'scanning' ? 'Scanning...' : scan.status === 'complete' ? 'Complete' : 'Failed'}
        </span>
      </div>

      {scan.status === 'scanning' && (
        <div className="scan-progress">
          <div className="scan-spinner" />
          <span>Scanning {scan.rootPath ?? 'files'}...</span>
        </div>
      )}

      {scan.status === 'complete' && (
        <ScanSummary
          fileCount={scan.fileCount}
          folderCount={scan.folderCount}
          newFiles={scan.newFiles}
          deletedFiles={scan.deletedFiles}
          categories={scan.categories}
        />
      )}

      {scan.status === 'failed' && (
        <p className="panel-error">Scan failed. Check the activity log for details.</p>
      )}
    </div>
  )
}
