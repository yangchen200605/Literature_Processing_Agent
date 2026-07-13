export type TaskType = 'summarize' | 'translate' | 'polish'

export interface ProcessRequest {
  text: string
  target_language?: string
}

export interface ProcessResponse {
  result: string
  task: string
}

export interface HealthResponse {
  status: string
  model: string
  api_configured: boolean
}
