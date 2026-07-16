import { useState } from 'react'
import { exportResult } from '../api/client'

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hul])/gm, (line) => (line.trim() ? `<p>${line}</p>` : ''))
}

interface ResultPanelProps {
  result: string
  loading: boolean
  error: string | null
  allowExport?: boolean
}

export default function ResultPanel({
  result,
  loading,
  error,
  allowExport = false,
}: ResultPanelProps) {
  const [exporting, setExporting] = useState<'docx' | 'pdf' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleCopy = async () => {
    if (result) await navigator.clipboard.writeText(result)
  }

  const handleExport = async (format: 'docx' | 'pdf') => {
    if (!result) return
    setExporting(format)
    setExportError(null)
    try {
      await exportResult(result, format)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : '导出失败')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 gap-2">
        <label className="text-sm font-medium text-slate-700">处理结果</label>
        {result && (
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {allowExport && (
              <>
                <button
                  type="button"
                  onClick={() => handleExport('docx')}
                  disabled={!!exporting}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-50"
                >
                  {exporting === 'docx' ? '导出中...' : '导出 Word'}
                </button>
                <button
                  type="button"
                  onClick={() => handleExport('pdf')}
                  disabled={!!exporting}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-50"
                >
                  {exporting === 'pdf' ? '导出中...' : '导出 PDF'}
                </button>
              </>
            )}
            <button
              type="button"
              onClick={handleCopy}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
            >
              复制结果
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 min-h-[280px] rounded-xl border border-slate-200 bg-white p-4 overflow-auto">
        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-sm">AI 正在处理中，请稍候...</p>
          </div>
        )}

        {(error || exportError) && !loading && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700 mb-3">
            {error || exportError}
          </div>
        )}

        {result && !loading && (
          <div
            className="markdown-body text-sm text-slate-800 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }}
          />
        )}

        {!result && !loading && !error && (
          <div className="flex items-center justify-center h-full text-sm text-slate-400">
            处理结果将显示在这里
          </div>
        )}
      </div>
    </div>
  )
}
