import type { HealthResponse, ParseDocumentResponse, ProcessRequest, ProcessResponse, TaskType } from '../types'

const API_BASE = '/api'

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item),
      )
      .join('; ')
  }
  return '请求失败'
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(formatErrorDetail(error.detail) || '请求失败')
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

export async function parseDocument(file: File): Promise<ParseDocumentResponse> {
  const form = new FormData()
  form.append('file', file)

  const response = await fetch(`${API_BASE}/parse-document`, {
    method: 'POST',
    body: form,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(formatErrorDetail(error.detail) || '解析文件失败')
  }

  return response.json()
}

export async function exportResult(content: string, format: 'docx' | 'pdf'): Promise<void> {
  const response = await fetch(`${API_BASE}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, format }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(formatErrorDetail(error.detail) || '导出失败')
  }

  const blob = await response.blob()
  const filename = format === 'docx' ? '文献摘要.docx' : '文献摘要.pdf'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
