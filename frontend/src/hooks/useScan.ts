import { useCallback, useState } from 'react'
import type { ScanResponse } from '../types/api'
import type { SSEEvent } from '../types/sse'

export interface ScanState {
  status: 'idle' | 'scanning' | 'complete' | 'failed'
  scanId: string | null
  rootPath: string | null
  scanDepth: string | null
  fileCount: number
  folderCount: number
  newFiles: number
  deletedFiles: number
  categories: Record<string, number>
  topFolders: string[]
}

const INITIAL: ScanState = {
  status: 'idle',
  scanId: null,
  rootPath: null,
  scanDepth: null,
  fileCount: 0,
  folderCount: 0,
  newFiles: 0,
  deletedFiles: 0,
  categories: {},
  topFolders: [],
}

export function useScan() {
  const [scan, setScan] = useState<ScanState>(INITIAL)

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.type === 'scan_started') {
      setScan({
        status: 'scanning',
        scanId: event.scan_id,
        rootPath: event.root_path,
        scanDepth: event.scan_depth,
        fileCount: 0,
        folderCount: 0,
        newFiles: 0,
        deletedFiles: 0,
        categories: {},
        topFolders: [],
      })
    } else if (event.type === 'scan_complete') {
      // Preserve rootPath from scan_started if the complete event doesn't carry it forward.
      setScan((prev) => ({
        status: 'complete',
        scanId: event.scan_id,
        rootPath: event.root_path || prev.rootPath,
        scanDepth: event.scan_depth || prev.scanDepth,
        fileCount: event.file_count,
        folderCount: event.folder_count,
        newFiles: event.new_files,
        deletedFiles: event.deleted_files,
        categories: event.categories,
        topFolders: event.top_folders ?? [],
      }))
    }
  }, [])

  const loadFromResponse = useCallback((scanResponse: ScanResponse) => {
    setScan({
      status: scanResponse.status === 'RUNNING' ? 'scanning' : scanResponse.status === 'COMPLETED' ? 'complete' : 'failed',
      scanId: scanResponse.id,
      rootPath: scanResponse.root_path,
      scanDepth: scanResponse.scan_depth,
      fileCount: scanResponse.file_count ?? 0,
      folderCount: scanResponse.folder_count ?? 0,
      newFiles: scanResponse.new_files,
      deletedFiles: scanResponse.deleted_files,
      categories: scanResponse.summary_json?.categories ?? {},
      topFolders: scanResponse.summary_json?.top_folders ?? [],
    })
  }, [])

  const reset = useCallback(() => setScan(INITIAL), [])

  return { scan, handleEvent, loadFromResponse, reset }
}
