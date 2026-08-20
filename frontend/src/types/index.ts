export type TaskType = 'summarize' | 'translate' | 'polish' | 'similar' | 'extract'

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
