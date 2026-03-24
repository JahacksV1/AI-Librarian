import { useCallback, useState } from 'react'
import type { ScanResponse } from '../types/api'
import type { SSEEvent } from '../types/sse'

export interface ScanState {
  status: 'idle' | 'scanning' | 'complete' | 'failed'
  scanId: string | null
  rootPath: string | null
  fileCount: number
  folderCount: number
  newFiles: number
  deletedFiles: number
  categories: Record<string, number>
}

const INITIAL: ScanState = {
  status: 'idle',
  scanId: null,
  rootPath: null,
  fileCount: 0,
  folderCount: 0,
  newFiles: 0,
  deletedFiles: 0,
  categories: {},
}

export function useScan() {
  const [scan, setScan] = useState<ScanState>(INITIAL)

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.type === 'scan_started') {
      setScan({
        status: 'scanning',
        scanId: event.scan_id,
        rootPath: event.root_path,
        fileCount: 0,
        folderCount: 0,
        newFiles: 0,
        deletedFiles: 0,
        categories: {},
      })
    } else if (event.type === 'scan_complete') {
      setScan({
        status: 'complete',
        scanId: event.scan_id,
        rootPath: null,
        fileCount: event.file_count,
        folderCount: event.folder_count,
        newFiles: event.new_files,
        deletedFiles: event.deleted_files,
        categories: event.categories,
      })
    }
  }, [])

  const loadFromResponse = useCallback((scanResponse: ScanResponse) => {
    setScan({
      status: scanResponse.status === 'RUNNING' ? 'scanning' : scanResponse.status === 'COMPLETED' ? 'complete' : 'failed',
      scanId: scanResponse.id,
      rootPath: scanResponse.root_path,
      fileCount: scanResponse.file_count ?? 0,
      folderCount: scanResponse.folder_count ?? 0,
      newFiles: scanResponse.new_files,
      deletedFiles: scanResponse.deleted_files,
      categories: scanResponse.summary_json?.categories ?? {},
    })
  }, [])

  const reset = useCallback(() => setScan(INITIAL), [])

  return { scan, handleEvent, loadFromResponse, reset }
}
