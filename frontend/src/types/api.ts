export interface HealthResponse {
  status: string
  db: string
  model_provider?: string
  model_name?: string
  model_status?: string
}

export interface SessionResponse {
  id: string
  user_id: string
  mode: string
  status: string
  title: string | null
  started_at: string | null
  updated_at: string | null
}

export interface PlanAction {
  id: string
  plan_id: string
  action_type: string
  action_payload_json: {
    from_path?: string
    to_path?: string
    path?: string
    [key: string]: unknown
  }
  status: string
}

export interface PlanResponse {
  id: string
  session_id: string
  goal: string
  rationale_summary: string
  status: string
  actions: PlanAction[]
}

export interface ScanResponse {
  id: string
  session_id: string | null
  device_id: string
  root_path: string
  scan_depth: string
  recursive: boolean
  file_count: number | null
  folder_count: number | null
  new_files: number
  deleted_files: number
  modified_files: number
  started_at: string | null
  completed_at: string | null
  status: string
  summary_json: {
    categories?: Record<string, number>
    top_folders?: string[]
    folder_child_counts?: Record<string, number>
  } | null
}

export interface FolderResponse {
  id: string
  canonical_path: string
  folder_name: string
  parent_path: string | null
  exists_now: boolean
}

export interface FileResponse {
  id: string
  canonical_path: string
  filename: string
  extension: string
  size_bytes: number
  exists_now: boolean
  modified_at: string | null
  guessed_category: string | null
  content_preview: string | null
}
