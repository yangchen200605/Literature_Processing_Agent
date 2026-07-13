import type { HealthResponse, ProcessRequest, ProcessResponse, TaskType } from '../types'

const API_BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || '请求失败')
  }

  return response.json()
}

export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export async function processText(
  task: TaskType,
  body: ProcessRequest,
): Promise<ProcessResponse> {
  return request<ProcessResponse>(`/${task}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
