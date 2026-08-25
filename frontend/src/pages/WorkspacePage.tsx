import { useEffect, useRef, useState } from 'react'
import {
  askRagStream,
  checkHealth,
  extractMetadata,
  findSimilarPapers,
  indexRagDocument,
  parseDocument,
  processTextStream,
} from '../api/client'
import TaskTabs from '../components/TaskTabs'
import TextInput from '../components/TextInput'
import ResultPanel from '../components/ResultPanel'
import SimilarPapersPanel from '../components/SimilarPapersPanel'
import ExtractPanel from '../components/ExtractPanel'
import RagPanel, { type RagSourceView } from '../components/RagPanel'
import { saveExtractToLibrary } from '../lib/library'
import type {
  ExtractedMetadata,
  ParseDocumentResponse,
  RagAgentStep,
  SimilarResponse,
  TaskType,
} from '../types'

const PLACEHOLDERS: Record<TaskType, string> = {
  summarize: '粘贴论文摘要、全文或章节内容，AI 将提炼结构化摘要（背景、目的、方法、发现、创新点等）...',
  extract: '粘贴论文摘要或全文，AI 将抽取标题、作者、年份、DOI、方法、数据集、指标等字段...',
  ask: '粘贴或上传 PDF/Word 全文，Agent 将自动规划检索、评估证据并作答...',
  translate: '粘贴需要翻译的学术文献内容（支持中英文互译）...',
  polish: '粘贴需要润色的学术文本，AI 将优化语法、用词和学术表达...',
  similar:
    '粘贴论文标题、摘要或正文片段；也可上传 PDF/Word。系统将通过 Semantic Scholar 检索并推荐相似文献...',
}

interface WorkspacePageProps {
  onOpenLibrary?: () => void
}

export default function WorkspacePage({ onOpenLibrary }: WorkspacePageProps) {
  const [task, setTask] = useState<TaskType>('summarize')
  const [input, setInput] = useState('')
  const [question, setQuestion] = useState('')
  const [targetLang, setTargetLang] = useState('中文')
  const [result, setResult] = useState('')
  const [extractData, setExtractData] = useState<ExtractedMetadata | null>(null)
  const [similarData, setSimilarData] = useState<SimilarResponse | null>(null)
  const [ragSources, setRagSources] = useState<RagSourceView[]>([])
  const [agentSteps, setAgentSteps] = useState<RagAgentStep[]>([])
  const [indexedDocId, setIndexedDocId] = useState<string | null>(null)
  const [indexHint, setIndexHint] = useState<string | null>(null)
  const [indexing, setIndexing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiReady, setApiReady] = useState<boolean | null>(null)
  const [model, setModel] = useState('')
  const [uploading, setUploading] = useState(false)
  const [documentMeta, setDocumentMeta] = useState<ParseDocumentResponse | null>(null)
  const [showExtractedText, setShowExtractedText] = useState(false)
  const [savedHint, setSavedHint] = useState<string | null>(null)
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
    setIndexedDocId(null)
    setIndexHint(null)
    setRagSources([])
    setAgentSteps([])
    setResult('')
  }

  const handleTaskChange = (next: TaskType) => {
    setTask(next)
    setError(null)
    setSavedHint(null)
    if (next !== 'summarize' && next !== 'similar' && next !== 'extract' && next !== 'ask') {
      clearDocument()
    }
    if (next !== 'ask') {
      setQuestion('')
      setRagSources([])
      setAgentSteps([])
      setIndexedDocId(null)
      setIndexHint(null)
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
      setExtractData(null)
      setSimilarData(null)
      setSavedHint(null)
      setIndexedDocId(null)
      setIndexHint(null)
      setRagSources([])
      setAgentSteps([])
    } catch (err) {
      setError(err instanceof Error ? err.message : '文件解析失败')
    } finally {
      setUploading(false)
    }
  }

  const handleIndex = async () => {
    if (!input.trim()) {
      setError('请先输入或上传文献内容')
      return
    }

    setIndexing(true)
    setError(null)
    setIndexHint(null)
    try {
      const response = await indexRagDocument({
        text: documentMeta ? undefined : input,
        file_id: documentMeta?.file_id,
        filename: documentMeta?.filename,
      })
      setIndexedDocId(response.doc_id)
      setIndexHint(
        `索引完成：${response.filename}，共 ${response.chunk_count} 个片段（${response.char_count.toLocaleString()} 字）`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '索引失败')
    } finally {
      setIndexing(false)
    }
  }

  const handleAsk = async () => {
    if (!indexedDocId) {
      setError('请先建立索引')
      return
    }
    if (!question.trim()) {
      setError('请输入问题')
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setStreaming(false)
    setError(null)
    setResult('')
    setRagSources([])
    setAgentSteps([])

    try {
      setStreaming(true)
      await askRagStream(
        {
          question: question.trim(),
          doc_ids: [indexedDocId],
        },
        {
          signal: controller.signal,
          onAgentStep: (step) => {
            setAgentSteps((prev) => [...prev, step])
          },
          onSources: (sources) => {
            setRagSources(sources)
          },
          onDelta: (text) => {
            setResult((prev) => prev + text)
          },
        },
      )
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('已取消生成')
      } else {
        setError(err instanceof Error ? err.message : '问答失败，请重试')
      }
    } finally {
      setLoading(false)
      setStreaming(false)
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  const handleSubmit = async () => {
    if (task === 'ask') {
      await handleAsk()
      return
    }

    if (!input.trim()) {
      setError(
        task === 'similar' || task === 'summarize' || task === 'extract'
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
    setExtractData(null)
    setSimilarData(null)
    setSavedHint(null)

    try {
      if (task === 'similar') {
        const response = await findSimilarPapers(input)
        setSimilarData(response)
      } else if (task === 'extract') {
        const data = await extractMetadata(input)
        setExtractData(data)
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

  const handleSaveExtract = () => {
    if (!extractData) return
    saveExtractToLibrary({
      extract: extractData,
      sourceFilename: documentMeta?.filename || null,
      textPreview: input,
    })
    setSavedHint('已保存到本地文献库。可在顶部「文献库」查看与批量导出。')
  }

  const handleCancel = () => {
    abortRef.current?.abort()
  }

  const allowUpload = task === 'summarize' || task === 'similar' || task === 'extract' || task === 'ask'

  const submitLabel = () => {
    if (task === 'ask') {
      if (loading) return streaming ? '生成中...' : '检索中...'
      return '提问'
    }
    if (!loading) {
      if (task === 'similar') return '查找相似文献'
      if (task === 'extract') return '开始抽取'
      return '开始处理'
    }
    if (task === 'similar') return '检索中...'
    if (task === 'extract') return '抽取中...'
    if (streaming) return '生成中...'
    return '处理中...'
  }

  return (
    <div className="space-y-6">
      {apiReady === false && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          请在后端 <code className="bg-amber-100 px-1 rounded">backend/.env</code> 中配置{' '}
          <code className="bg-amber-100 px-1 rounded">DEEPSEEK_API_KEY</code>，并启动后端服务。
        </div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-slate-500">
          当前模型：{apiReady && model ? model : apiReady === false ? '未配置' : '检测中...'}
        </p>
        {onOpenLibrary && (
          <button
            type="button"
            onClick={onOpenLibrary}
            className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
          >
            打开文献库 →
          </button>
        )}
      </div>

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
          disabled={loading || indexing}
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
        ) : task === 'extract' ? (
          <ExtractPanel
            data={extractData}
            loading={loading}
            error={error}
            savedHint={savedHint}
            onSave={handleSaveExtract}
          />
        ) : task === 'ask' ? (
          <RagPanel
            question={question}
            onQuestionChange={setQuestion}
            result={result}
            sources={ragSources}
            agentSteps={agentSteps}
            loading={loading}
            streaming={streaming}
            indexing={indexing}
            indexedDocId={indexedDocId}
            indexHint={indexHint}
            error={error}
            disabled={loading || indexing}
          />
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

      <div className="flex justify-center gap-3 flex-wrap">
        {task === 'ask' && (
          <button
            type="button"
            onClick={handleIndex}
            disabled={indexing || loading || uploading || !input.trim()}
            className="px-6 py-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-700 font-medium text-sm hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {indexing ? '索引中...' : indexedDocId ? '重新建立索引' : '建立索引'}
          </button>
        )}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={
            loading ||
            uploading ||
            indexing ||
            (task === 'ask' ? !question.trim() || !indexedDocId : !input.trim())
          }
          className="px-8 py-3 rounded-xl bg-indigo-600 text-white font-medium text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm shadow-indigo-600/20"
        >
          {submitLabel()}
        </button>
        {loading && task !== 'similar' && task !== 'extract' && (
          <button
            type="button"
            onClick={handleCancel}
            className="px-6 py-3 rounded-xl border border-slate-300 bg-white text-slate-700 font-medium text-sm hover:bg-slate-50"
          >
            停止
          </button>
        )}
      </div>
    </div>
  )
}
