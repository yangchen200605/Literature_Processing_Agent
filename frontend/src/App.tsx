import { useEffect, useState } from 'react'
import { checkHealth, parseDocument, processText } from './api/client'
import TaskTabs from './components/TaskTabs'
import TextInput from './components/TextInput'
import ResultPanel from './components/ResultPanel'
import type { TaskType } from './types'

const PLACEHOLDERS: Record<TaskType, string> = {
  summarize: '粘贴论文摘要、全文或章节内容，AI 将提炼结构化摘要（背景、目的、方法、发现、创新点等）...',
  translate: '粘贴需要翻译的学术文献内容（支持中英文互译）...',
  polish: '粘贴需要润色的学术文本，AI 将优化语法、用词和学术表达...',
}

export default function App() {
  const [task, setTask] = useState<TaskType>('summarize')
  const [input, setInput] = useState('')
  const [targetLang, setTargetLang] = useState('中文')
  const [result, setResult] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiReady, setApiReady] = useState<boolean | null>(null)
  const [model, setModel] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadedName, setUploadedName] = useState<string | null>(null)

  useEffect(() => {
    checkHealth()
      .then((data) => {
        setApiReady(data.api_configured)
        setModel(data.model)
      })
      .catch(() => setApiReady(false))
  }, [])

  const handleTaskChange = (next: TaskType) => {
    setTask(next)
    setError(null)
    if (next !== 'summarize') {
      setUploadedName(null)
    }
  }

  const handleFileSelect = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const data = await parseDocument(file)
      setInput(data.text)
      setUploadedName(data.filename)
      setResult('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '文件解析失败')
    } finally {
      setUploading(false)
    }
  }

  const handleSubmit = async () => {
    if (!input.trim()) {
      setError('请输入文献内容，或上传 PDF / Word 文件')
      return
    }

    setLoading(true)
    setError(null)
    setResult('')

    try {
      const response = await processText(task, {
        text: input,
        ...(task === 'translate' ? { target_language: targetLang } : {}),
      })
      setResult(response.result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '处理失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
      <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">文献处理 Agent</h1>
            <p className="text-sm text-slate-500">摘要提炼 · 学术翻译 · 润色优化</p>
          </div>
          <div className="flex items-center gap-2">
            {apiReady === false && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-amber-100 text-amber-700">
                API 未配置
              </span>
            )}
            {apiReady && model && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700">
                {model}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {apiReady === false && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            请在后端 <code className="bg-amber-100 px-1 rounded">backend/.env</code> 中配置{' '}
            <code className="bg-amber-100 px-1 rounded">DEEPSEEK_API_KEY</code>，并启动后端服务。
          </div>
        )}

        <TaskTabs active={task} onChange={handleTaskChange} />

        {task === 'translate' && (
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-slate-700">目标语言</label>
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="中文">中文</option>
              <option value="English">English</option>
              <option value="日本語">日本語</option>
              <option value="한국어">한국어</option>
              <option value="Français">Français</option>
              <option value="Deutsch">Deutsch</option>
            </select>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TextInput
            value={input}
            onChange={setInput}
            placeholder={PLACEHOLDERS[task]}
            disabled={loading}
            allowUpload={task === 'summarize'}
            uploading={uploading}
            uploadedName={task === 'summarize' ? uploadedName : null}
            onFileSelect={handleFileSelect}
            onClearFile={() => setUploadedName(null)}
          />
          <ResultPanel
            result={result}
            loading={loading}
            error={error}
            allowExport={task === 'summarize'}
          />
        </div>

        <div className="flex justify-center">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading || uploading || !input.trim()}
            className="px-8 py-3 rounded-xl bg-indigo-600 text-white font-medium text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm shadow-indigo-600/20"
          >
            {loading ? '处理中...' : '开始处理'}
          </button>
        </div>
      </main>
    </div>
  )
}
