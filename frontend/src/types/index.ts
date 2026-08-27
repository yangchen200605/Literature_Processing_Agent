export type TaskType = 'summarize' | 'translate' | 'polish' | 'similar' | 'extract' | 'ask'

export type AppPage = 'workspace' | 'library'

export interface ProcessRequest {
  text: string
  target_language?: string
}

export interface ProcessResponse {
  result: string
  task: string
}

export interface ImagePreview {
  label: string
  data_url: string
}

export interface ParseDocumentResponse {
  file_id: string
  filename: string
  file_type: string
  text: string
  cover_url?: string | null
  cover_data_url?: string | null
  download_url: string
  page_count: number
  table_count: number
  image_count: number
  char_count: number
  image_previews: ImagePreview[]
}

export interface HealthResponse {
  status: string
  model: string
  api_configured: boolean
  scholar_api_configured?: boolean
  mcp_configured?: boolean
  mcp_tools?: string[]
  mcp_mode?: string
}

export interface PaperItem {
  paper_id: string
  title: string
  abstract?: string | null
  tldr?: string | null
  year?: number | null
  citation_count?: number | null
  venue?: string | null
  authors: string[]
  url?: string | null
  doi?: string | null
  open_access_pdf?: string | null
}

export interface SimilarResponse {
  query: string
  seed: PaperItem | null
  papers: PaperItem[]
  message?: string | null
  via?: string | null
}

export interface ExtractedMetadata {
  title: string | null
  authors: string[]
  year: number | null
  doi: string | null
  venue: string | null
  keywords: string[]
  methods: string[]
  datasets: string[]
  metrics: string[]
  contribution: string | null
}

export interface LibraryRecord {
  id: string
  createdAt: string
  updatedAt: string
  sourceFilename?: string | null
  sourceNote?: string | null
  textPreview?: string | null
  extract: ExtractedMetadata
  summary?: string | null
}

export interface RagIndexResponse {
  doc_id: string
  filename: string
  chunk_count: number
  char_count: number
  indexed_at: number
}

export interface RagDocumentItem {
  doc_id: string
  filename: string
  chunk_count: number
  char_count: number
  indexed_at: number
}

export interface RagSourceItem {
  index: number
  doc_id: string
  filename: string
  text: string
  page?: number | null
  char_start?: number
  char_end?: number
  score?: number | null
}

export interface HitlReviewPayload {
  run_id: string
  stage: 'plan_review' | 'answer_review' | string
  message: string
  analysis?: string
  search_queries?: string[]
  source_count?: number
  session_id?: string | null
}

export interface RagAgentStep {
  phase: 'plan' | 'retrieve' | 'grade' | 'answer' | 'turn_complete' | string
  message: string
  detail?: Record<string, unknown> | null
  agent?: string
}

export interface MemorySessionResponse {
  session_id: string
  doc_ids: string[]
  created_at: number
  updated_at: number
  checkpoint_count: number
  turn_count: number
}
