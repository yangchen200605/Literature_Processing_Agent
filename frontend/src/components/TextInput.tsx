interface TextInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  allowUpload?: boolean
  uploading?: boolean
  uploadedName?: string | null
  onFileSelect?: (file: File) => void
  onClearFile?: () => void
}

export default function TextInput({
  value,
  onChange,
  placeholder,
  disabled,
  allowUpload = false,
  uploading = false,
  uploadedName = null,
  onFileSelect,
  onClearFile,
}: TextInputProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 gap-2">
        <label className="text-sm font-medium text-slate-700">输入文献内容</label>
        {allowUpload && (
          <div className="flex items-center gap-2">
            <label
              className={`text-xs font-medium px-2.5 py-1 rounded-lg border cursor-pointer transition-colors ${
                disabled || uploading
                  ? 'border-slate-200 text-slate-400 cursor-not-allowed'
                  : 'border-indigo-200 text-indigo-600 hover:bg-indigo-50'
              }`}
            >
              {uploading ? '解析中...' : '上传 PDF / Word'}
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
            {uploadedName && (
              <button
                type="button"
                onClick={onClearFile}
                disabled={disabled || uploading}
                className="text-xs text-slate-500 hover:text-slate-700"
              >
                清除
              </button>
            )}
          </div>
        )}
      </div>

      {allowUpload && uploadedName && (
        <div className="mb-2 text-xs text-slate-500 truncate">
          已载入：<span className="text-slate-700 font-medium">{uploadedName}</span>
        </div>
      )}

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          allowUpload
            ? `${placeholder ?? ''}\n\n也可点击右上角上传 PDF 或 Word 文件。`
            : placeholder
        }
        disabled={disabled || uploading}
        className="flex-1 min-h-[280px] w-full resize-none rounded-xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:text-slate-500"
      />
      <div className="mt-2 text-xs text-slate-400 text-right">{value.length} 字符</div>
    </div>
  )
}
