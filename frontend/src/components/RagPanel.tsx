import { useState } from 'react'
import type { RagAgentStep } from '../types'

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

export interface RagSourceView {
  index: number
  doc_id: string
  filename: string
  text: string
  page?: number | null
  score?: number | null
}

const PHASE_META: Record<string, { icon: string; label: string }> = {
  plan: { icon: '🧭', label: '规划' },
  retrieve: { icon: '🔍', label: '检索' },
  grade: { icon: '⚖️', label: '评估' },
  answer: { icon: '✍️', label: '作答' },
}

function phaseLabel(phase: string): string {
  return PHASE_META[phase]?.label || phase
}

function phaseIcon(phase: string): string {
  return PHASE_META[phase]?.icon || '•'
}

interface RagPanelProps {
  question: string
  onQuestionChange: (value: string) => void
  result: string
  sources: RagSourceView[]
  agentSteps: RagAgentStep[]
  loading: boolean
  streaming: boolean
  indexing: boolean
  indexedDocId: string | null
  indexHint: string | null
  error: string | null
  disabled?: boolean
}

export default function RagPanel({
  question,
  onQuestionChange,
  result,
  sources,
  agentSteps,
  loading,
  streaming,
  indexing,
  indexedDocId,
  indexHint,
  error,
  disabled = false,
}: RagPanelProps) {
  const [expandedSource, setExpandedSource] = useState<number | null>(null)

  const handleCopy = async () => {
    if (result) await navigator.clipboard.writeText(result)
  }

  const showAgentTimeline = loading || agentSteps.length > 0

  return (
    <div className="flex flex-col h-full gap-3">
      <div>
        <label className="text-sm font-medium text-slate-700 mb-1 block">你的问题</label>
        <textarea
          value={question}
          onChange={(e) => onQuestionChange(e.target.value)}
          disabled={disabled || loading || indexing}
          placeholder="例如：本文使用了哪些数据集？方法与实验结果有何关联？"
          className="w-full min-h-[88px] rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-60"
        />
      </div>

      <div className="flex items-center gap-2 flex-wrap text-xs">
        {indexing && (
          <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">正在建立索引...</span>
        )}
        {indexedDocId && !indexing && (
          <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
            已索引 · {indexedDocId.slice(0, 8)}…
          </span>
        )}
        {loading && !streaming && (
          <span className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-700">Agent 推理中</span>
        )}
        {streaming && (
          <span className="px-2 py-0.5 rounded-full bg-violet-50 text-violet-700">SSE 流式输出中</span>
        )}
      </div>

      {indexHint && !error && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-100 px-3 py-2 text-xs text-indigo-800">
          {indexHint}
        </div>
      )}

      {showAgentTimeline && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 max-h-40 overflow-auto">
          <p className="text-xs font-medium text-slate-600 mb-2">Agent 推理轨迹</p>
          {agentSteps.length === 0 && loading && (
            <p className="text-xs text-slate-500">正在规划检索策略…</p>
          )}
          <div className="space-y-2">
            {agentSteps.map((step, idx) => {
              const queries = Array.isArray(step.detail?.search_queries)
                ? (step.detail?.search_queries as string[])
                : Array.isArray(step.detail?.queries)
                  ? (step.detail?.queries as string[])
                  : Array.isArray(step.detail?.follow_up_queries)
                    ? (step.detail?.follow_up_queries as string[])
                    : []
              return (
                <div key={`${step.phase}-${idx}`} className="rounded-lg bg-white border border-slate-200 px-2 py-1.5">
                  <p className="text-xs text-slate-800">
                    <span className="mr-1">{phaseIcon(step.phase)}</span>
                    <span className="font-medium">{phaseLabel(step.phase)}</span>
                    <span className="text-slate-500"> · {step.message}</span>
                  </p>
                  {typeof step.detail?.analysis === 'string' && (
                    <p className="text-[11px] text-slate-500 mt-0.5">{step.detail.analysis}</p>
                  )}
                  {queries.length > 0 && (
                    <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                      查询：{queries.join(' · ')}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-[180px] rounded-xl border border-slate-200 bg-white p-4 overflow-auto">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-slate-700">回答</label>
          {result && !streaming && (
            <button
              type="button"
              onClick={handleCopy}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
            >
              复制回答
            </button>
          )}
        </div>

        {loading && !result && agentSteps.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 gap-3 text-slate-500">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-sm">Agent 正在检索并生成回答...</p>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700 mb-3">
            {error}
          </div>
        )}

        {result && (
          <div
            className="markdown-body text-sm text-slate-800 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }}
          />
        )}

        {result && streaming && (
          <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-indigo-500 animate-pulse" />
        )}

        {!result && !loading && !error && (
          <div className="flex items-center justify-center h-24 text-sm text-slate-400">
            先建立索引，Agent 将自动规划多轮检索后作答
          </div>
        )}
      </div>

      {sources.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 max-h-40 overflow-auto">
          <p className="text-xs font-medium text-slate-600 mb-2">引用片段 ({sources.length})</p>
          <div className="space-y-2">
            {sources.map((source) => {
              const open = expandedSource === source.index
              const location = source.page ? `第${source.page}页` : '正文'
              return (
                <div key={source.index} className="rounded-lg bg-white border border-slate-200 p-2">
                  <button
                    type="button"
                    onClick={() => setExpandedSource(open ? null : source.index)}
                    className="w-full text-left text-xs text-slate-700 font-medium"
                  >
                    [{source.index}] {source.filename} · {location}
                    {source.score != null && (
                      <span className="ml-2 text-slate-400">相关度 {(source.score * 100).toFixed(0)}%</span>
                    )}
                  </button>
                  {open && (
                    <p className="mt-2 text-xs text-slate-600 whitespace-pre-wrap leading-relaxed">
                      {source.text}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
