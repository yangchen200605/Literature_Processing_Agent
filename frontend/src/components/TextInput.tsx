import type { ParseDocumentResponse } from '../types'
import DocumentPreview from './DocumentPreview'

interface TextInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  allowUpload?: boolean
  uploading?: boolean
  document?: ParseDocumentResponse | null
  showExtractedText?: boolean
  onToggleExtractedText?: () => void
  onFileSelect?: (file: File) => void
  onClearDocument?: () => void
}

export default function TextInput({
  value,
  onChange,
  placeholder,
  disabled,
  allowUpload = false,
  uploading = false,
  document = null,
  showExtractedText = false,
  onToggleExtractedText,
  onFileSelect,
  onClearDocument,
}: TextInputProps) {
  const hasDocument = allowUpload && !!document

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 gap-2">
        <label className="text-sm font-medium text-slate-700">
          {hasDocument ? '文献文档' : '输入文献内容'}
        </label>
        {allowUpload && (
          <label
            className={`text-xs font-medium px-2.5 py-1 rounded-lg border cursor-pointer transition-colors ${
              disabled || uploading
                ? 'border-slate-200 text-slate-400 cursor-not-allowed'
                : 'border-indigo-200 text-indigo-600 hover:bg-indigo-50'
            }`}
          >
            {uploading ? '解析中...' : hasDocument ? '更换 PDF / Word' : '上传 PDF / Word'}
            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              disabled={disabled || uploading}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file && onFileSelect) onFileSelect(file)
              }}
            />
          </label>
        )}
      </div>

      {hasDocument && document ? (
        <DocumentPreview
          doc={document}
          disabled={disabled || uploading}
          showExtractedText={showExtractedText}
          onToggleText={() => onToggleExtractedText?.()}
          onClear={() => onClearDocument?.()}
        />
      ) : (
        <>
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={
              allowUpload
                ? `${placeholder ?? ''}\n\n也可点击右上角上传 PDF 或 Word（将显示封面预览，支持下载原文件）。`
                : placeholder
            }
            disabled={disabled || uploading}
            className="flex-1 min-h-[280px] w-full resize-none rounded-xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:text-slate-500"
          />
          <div className="mt-2 text-xs text-slate-400 text-right">{value.length} 字符</div>
        </>
      )}
    </div>
  )
}
