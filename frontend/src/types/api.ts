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
