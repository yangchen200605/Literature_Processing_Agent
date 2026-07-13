interface TextInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

export default function TextInput({ value, onChange, placeholder, disabled }: TextInputProps) {
  return (
    <div className="flex flex-col h-full">
      <label className="text-sm font-medium text-slate-700 mb-2">输入文献内容</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 min-h-[280px] w-full resize-none rounded-xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:text-slate-500"
      />
      <div className="mt-2 text-xs text-slate-400 text-right">{value.length} 字符</div>
    </div>
  )
}
