import { useEffect, useRef, useState } from 'react'
import { checkHealth, findSimilarPapers, parseDocument, processTextStream } from './api/client'
import TaskTabs from './components/TaskTabs'
import TextInput from './components/TextInput'
import ResultPanel from './components/ResultPanel'
import SimilarPapersPanel from './components/SimilarPapersPanel'
import type { ParseDocumentResponse, SimilarResponse, TaskType } from './types'

const PLACEHOLDERS: Record<TaskType, string> = {
  summarize: '粘贴论文摘要、全文或章节内容，AI 将提炼结构化摘要（背景、目的、方法、发现、创新点等）...',
  translate: '粘贴需要翻译的学术文献内容（支持中英文互译）...',
  polish: '粘贴需要润色的学术文本，AI 将优化语法、用词和学术表达...',
  similar:
    '粘贴论文标题、摘要或正文片段；也可上传 PDF/Word。系统将通过 Semantic Scholar 检索并推荐相似文献...',
}

export default function App() {
  const [task, setTask] = useState<TaskType>('summarize')
  const [input, setInput] = useState('')
  const [targetLang, setTargetLang] = useState('中文')
  const [result, setResult] = useState('')
  const [similarData, setSimilarData] = useState<SimilarResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiReady, setApiReady] = useState<boolean | null>(null)
  const [model, setModel] = useState('')
  const [uploading, setUploading] = useState(false)
  const [documentMeta, setDocumentMeta] = useState<ParseDocumentResponse | null>(null)
  const [showExtractedText, setShowExtractedText] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    checkHealth()
      .then((data) => {
        setApiReady(data.api_configured)
        setModel(data.model)
      })
      .catch(() => setApiReady(false))

    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const clearDocument = () => {
    setDocumentMeta(null)
    setShowExtractedText(false)
    setInput('')
  }

  const handleTaskChange = (next: TaskType) => {
    setTask(next)
    setError(null)
    if (next !== 'summarize' && next !== 'similar') {
      clearDocument()
    }
  }

  const handleFileSelect = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const data = await parseDocument(file)
      setDocumentMeta(data)
      setInput(data.text)
      setShowExtractedText(false)
      setResult('')
      setSimilarData(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '文件解析失败')
    } finally {
      setUploading(false)
    }
  }

  const handleSubmit = async () => {
    if (!input.trim()) {
      setError(
        task === 'similar' || task === 'summarize'
          ? '请输入文献内容，或上传 PDF / Word 文件'
          : '请输入文献内容',
      )
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setStreaming(false)
    setError(null)
    setResult('')
    setSimilarData(null)

    try {
      if (task === 'similar') {
        const response = await findSimilarPapers(input)
        setSimilarData(response)
      } else {
        setStreaming(true)
        await processTextStream(
          task,
          {
            text: input,
            ...(task === 'translate' ? { target_language: targetLang } : {}),
          },
          {
            signal: controller.signal,
            onDelta: (text) => {
              setResult((prev) => prev + text)
            },
          },
        )
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('已取消生成')
      } else {
        setError(err instanceof Error ? err.message : '处理失败，请重试')
      }
    } finally {
      setLoading(false)
      setStreaming(false)
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  const handleCancel = () => {
    abortRef.current?.abort()
  }

  const allowUpload = task === 'summarize' || task === 'similar'

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
      <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">文献处理 Agent</h1>
            <p className="text-sm text-slate-500">摘要提炼 · 学术翻译 · 润色优化 · 找类似文献</p>
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
            找类似文献依赖 Semantic Scholar；长文/中文会用 DeepSeek 提炼英文检索式。
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
            allowUpload={allowUpload}
            uploading={uploading}
            document={allowUpload ? documentMeta : null}
            showExtractedText={showExtractedText}
            onToggleExtractedText={() => setShowExtractedText((v) => !v)}
            onFileSelect={handleFileSelect}
            onClearDocument={clearDocument}
          />
          {task === 'similar' ? (
            <SimilarPapersPanel data={similarData} loading={loading} error={error} />
          ) : (
            <ResultPanel
              result={result}
              loading={loading}
              streaming={streaming}
              error={error}
              allowExport={task === 'summarize'}
            />
          )}
        </div>

        <div className="flex justify-center gap-3">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading || uploading || !input.trim()}
            className="px-8 py-3 rounded-xl bg-indigo-600 text-white font-medium text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm shadow-indigo-600/20"
          >
            {loading
              ? task === 'similar'
                ? '检索中...'
                : streaming
                  ? '生成中...'
                  : '处理中...'
              : task === 'similar'
                ? '查找相似文献'
                : '开始处理'}
          </button>
          {loading && task !== 'similar' && (
            <button
              type="button"
              onClick={handleCancel}
              className="px-6 py-3 rounded-xl border border-slate-300 bg-white text-slate-700 font-medium text-sm hover:bg-slate-50"
            >
              停止
            </button>
          )}
        </div>
      </main>
    </div>
  )
}
