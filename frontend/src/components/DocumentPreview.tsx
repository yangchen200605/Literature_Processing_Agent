import type { ParseDocumentResponse } from '../types'

interface DocumentPreviewProps {
  doc: ParseDocumentResponse
  disabled?: boolean
  showExtractedText: boolean
  onToggleText: () => void
  onClear: () => void
}

function formatSize(chars: number): string {
  if (chars >= 10000) return `${(chars / 10000).toFixed(1)} 万字`
  return `${chars} 字`
}

export default function DocumentPreview({
  doc,
  disabled,
  showExtractedText,
  onToggleText,
  onClear,
}: DocumentPreviewProps) {
  const cover = doc.cover_data_url || doc.cover_url || null
  const downloadHref = doc.download_url.startsWith('http')
    ? doc.download_url
    : doc.download_url

  return (
    <div className="flex flex-col gap-3 flex-1 min-h-[280px]">
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="grid grid-cols-[140px_1fr] sm:grid-cols-[160px_1fr]">
          <div className="bg-slate-100 border-r border-slate-200 flex items-center justify-center min-h-[200px] p-2">
            {cover ? (
              <img
                src={cover}
                alt="文档封面"
                className="max-h-[220px] w-full object-contain rounded-sm shadow-sm"
              />
            ) : (
              <div className="text-xs text-slate-400 text-center px-3">暂无封面预览</div>
            )}
          </div>

          <div className="p-4 flex flex-col gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">
                {doc.file_type.toUpperCase()} 文献
              </p>
              <h3 className="text-sm font-semibold text-slate-900 break-all leading-snug">
                {doc.filename}
              </h3>
            </div>

            <div className="flex flex-wrap gap-2 text-[11px]">
              {doc.page_count > 0 && (
                <span className="px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                  {doc.page_count} 页
                </span>
              )}
              <span className="px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                {doc.table_count} 表格
              </span>
              <span className="px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                {doc.image_count} 图片
              </span>
              <span className="px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                {formatSize(doc.char_count)}
              </span>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed">
              已解析正文、表格（Markdown）与图片占位。处理时将使用提取内容；此处以封面展示文档，不再整页堆纯文字。
            </p>

            <div className="mt-auto flex flex-wrap gap-2">
              <a
                href={downloadHref}
                download={doc.filename}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 ${
                  disabled ? 'pointer-events-none opacity-50' : ''
                }`}
              >
                下载原文件
              </a>
              <button
                type="button"
                onClick={onToggleText}
                disabled={disabled}
                className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {showExtractedText ? '收起提取文本' : '查看提取文本'}
              </button>
              <button
                type="button"
                onClick={onClear}
                disabled={disabled}
                className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
              >
                移除
              </button>
            </div>
          </div>
        </div>
      </div>

      {doc.image_previews?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-600 mb-2">文档内图片预览</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {doc.image_previews.map((img) => (
              <figure
                key={img.label}
                className="shrink-0 w-28 rounded-lg border border-slate-200 bg-white overflow-hidden"
              >
                <img src={img.data_url} alt={img.label} className="h-24 w-full object-cover" />
                <figcaption className="text-[10px] text-slate-500 px-1.5 py-1 truncate">
                  {img.label}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      {showExtractedText && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 max-h-56 overflow-auto">
          <p className="text-xs font-medium text-slate-600 mb-2">供 AI 使用的提取文本（含表格）</p>
          <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">
            {doc.text}
          </pre>
        </div>
      )}
    </div>
  )
}
