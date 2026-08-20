import type { ExtractedMetadata, LibraryRecord } from '../types'

const STORAGE_KEY = 'literature_agent_library_v1'

function readAll(): LibraryRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const data = JSON.parse(raw) as LibraryRecord[]
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}

function writeAll(records: LibraryRecord[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
}

export function listLibraryRecords(): LibraryRecord[] {
  return readAll().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function saveExtractToLibrary(input: {
  extract: ExtractedMetadata
  sourceFilename?: string | null
  sourceNote?: string | null
  textPreview?: string | null
  summary?: string | null
}): LibraryRecord {
  const now = new Date().toISOString()
  const record: LibraryRecord = {
    id: crypto.randomUUID(),
    createdAt: now,
    updatedAt: now,
    sourceFilename: input.sourceFilename || null,
    sourceNote: input.sourceNote || null,
    textPreview: input.textPreview?.slice(0, 500) || null,
    extract: input.extract,
    summary: input.summary || null,
  }
  const all = readAll()
  all.unshift(record)
  writeAll(all)
  return record
}

export function updateLibraryRecord(id: string, patch: Partial<LibraryRecord>): LibraryRecord | null {
  const all = readAll()
  const idx = all.findIndex((r) => r.id === id)
  if (idx < 0) return null
  const next = {
    ...all[idx],
    ...patch,
    id: all[idx].id,
    createdAt: all[idx].createdAt,
    updatedAt: new Date().toISOString(),
  }
  all[idx] = next
  writeAll(all)
  return next
}

export function deleteLibraryRecord(id: string): void {
  writeAll(readAll().filter((r) => r.id !== id))
}

export function clearLibrary(): void {
  writeAll([])
}

function csvEscape(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

export function extractToCsvRows(records: ExtractedMetadata[]): string {
  const header = [
    'title',
    'authors',
    'year',
    'doi',
    'venue',
    'keywords',
    'methods',
    'datasets',
    'metrics',
    'contribution',
  ]
  const lines = [header.join(',')]
  for (const item of records) {
    lines.push(
      [
        item.title || '',
        item.authors.join('; '),
        item.year == null ? '' : String(item.year),
        item.doi || '',
        item.venue || '',
        item.keywords.join('; '),
        item.methods.join('; '),
        item.datasets.join('; '),
        item.metrics.join('; '),
        item.contribution || '',
      ]
        .map((v) => csvEscape(v))
        .join(','),
    )
  }
  return lines.join('\n')
}

export function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function downloadExtractJson(data: ExtractedMetadata | ExtractedMetadata[], filename = 'literature-extract.json') {
  downloadTextFile(filename, JSON.stringify(data, null, 2), 'application/json;charset=utf-8')
}

export function downloadExtractCsv(data: ExtractedMetadata[], filename = 'literature-extract.csv') {
  // BOM for Excel
  downloadTextFile(filename, `\uFEFF${extractToCsvRows(data)}`, 'text/csv;charset=utf-8')
}

export function downloadLibraryCsv(records: LibraryRecord[], filename = 'literature-library.csv') {
  const header = [
    'id',
    'createdAt',
    'sourceFilename',
    'title',
    'authors',
    'year',
    'doi',
    'venue',
    'keywords',
    'methods',
    'datasets',
    'metrics',
    'contribution',
  ]
  const lines = [header.join(',')]
  for (const r of records) {
    const e = r.extract
    lines.push(
      [
        r.id,
        r.createdAt,
        r.sourceFilename || '',
        e.title || '',
        e.authors.join('; '),
        e.year == null ? '' : String(e.year),
        e.doi || '',
        e.venue || '',
        e.keywords.join('; '),
        e.methods.join('; '),
        e.datasets.join('; '),
        e.metrics.join('; '),
        e.contribution || '',
      ]
        .map((v) => csvEscape(v))
        .join(','),
    )
  }
  downloadTextFile(filename, `\uFEFF${lines.join('\n')}`, 'text/csv;charset=utf-8')
}
