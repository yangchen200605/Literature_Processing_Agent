import type { ReactNode } from 'react'
import type { ExtractedMetadata } from '../types'
import { downloadExtractCsv, downloadExtractJson } from '../lib/library'

interface ExtractPanelProps {
  data: ExtractedMetadata | null
  loading: boolean
  error: string | null
  savedHint?: string | null
  onSave?: () => void
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-800">{children}</dd>
    </div>
  )
}

function Tags({ items }: { items: string[] }) {
  if (!items.length) return <span className="text-slate-400">未提及</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-xs"
        >
          {item}
        </span>
      ))}
    </div>
  )
}

export default function ExtractPanel({
  data,
  loading,
  error,
  savedHint,
  onSave,
}: ExtractPanelProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 gap-2">
        <label className="text-sm font-medium text-slate-700">结构化字段</label>
        {data && (
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <button
              type="button"
              onClick={() => downloadExtractJson(data)}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
            >
              导出 JSON
            </button>
            <button
              type="button"
              onClick={() => downloadExtractCsv([data])}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
            >
              导出 CSV
            </button>
            {onSave && (
              <button
                type="button"
                onClick={onSave}
                className="text-xs text-emerald-700 hover:text-emerald-900 font-medium"
              >
                保存到文献库
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-[280px] rounded-xl border border-slate-200 bg-white p-4 overflow-auto">
        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-sm">正在抽取关键信息...</p>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {savedHint && !loading && (
          <div className="mb-3 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-800">
            {savedHint}
          </div>
        )}

        {data && !loading && (
          <dl className="space-y-4">
            <Field label="标题">{data.title || '未提及'}</Field>
            <Field label="作者">
              <Tags items={data.authors} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="年份">{data.year ?? '未提及'}</Field>
              <Field label="DOI">{data.doi || '未提及'}</Field>
            </div>
            <Field label="期刊/会议">{data.venue || '未提及'}</Field>
            <Field label="关键词">
              <Tags items={data.keywords} />
            </Field>
            <Field label="方法">
              <Tags items={data.methods} />
            </Field>
            <Field label="数据集">
              <Tags items={data.datasets} />
            </Field>
            <Field label="指标">
              <Tags items={data.metrics} />
            </Field>
            <Field label="贡献概述">{data.contribution || '未提及'}</Field>
          </dl>
        )}

        {!data && !loading && !error && (
          <div className="flex items-center justify-center h-full text-sm text-slate-400">
            抽取结果将显示在这里，可导出 JSON / CSV
          </div>
        )}
      </div>
    </div>
  )
}
