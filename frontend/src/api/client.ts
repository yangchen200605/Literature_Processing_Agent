import type {
  HealthResponse,
  ParseDocumentResponse,
  ProcessRequest,
  SimilarResponse,
  TaskType,
} from '../types'

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

export interface StreamHandlers {
  onStart?: (task: string) => void
  onDelta: (text: string) => void
  onDone?: (task: string) => void
  signal?: AbortSignal
}

/** 摘要 / 翻译 / 润色：SSE 流式处理 */
export async function processTextStream(
  task: Exclude<TaskType, 'similar'>,
  body: ProcessRequest,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_BASE}/${task}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(formatErrorDetail(error.detail) || '请求失败')
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let sawError: string | null = null

  const handleBlock = (block: string) => {
    const lines = block.split('\n')
    let event = 'message'
    const dataLines: string[] = []
    for (const line of lines) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }
    if (!dataLines.length) return
    let payload: Record<string, unknown> = {}
    try {
      payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
    } catch {
      return
    }

    if (event === 'start') {
      handlers.onStart?.(String(payload.task || task))
    } else if (event === 'delta' && typeof payload.text === 'string') {
      handlers.onDelta(payload.text)
    } else if (event === 'done') {
      handlers.onDone?.(String(payload.task || task))
    } else if (event === 'error') {
      sawError = formatErrorDetail(payload.detail) || '流式处理失败'
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      if (part.trim()) handleBlock(part)
    }
  }
  if (buffer.trim()) handleBlock(buffer)

  if (sawError) {
    throw new Error(sawError)
  }
}

export async function findSimilarPapers(text: string, limit = 8): Promise<SimilarResponse> {
  return request<SimilarResponse>('/similar-papers', {
    method: 'POST',
    body: JSON.stringify({ text, limit }),
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
