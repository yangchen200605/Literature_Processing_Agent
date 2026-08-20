import { useMemo, useState } from 'react'
import type { LibraryRecord } from '../types'
import {
  clearLibrary,
  deleteLibraryRecord,
  downloadExtractJson,
  downloadLibraryCsv,
  listLibraryRecords,
} from '../lib/library'

interface LibraryPageProps {
  onBack?: () => void
}

export default function LibraryPage({ onBack }: LibraryPageProps) {
  const [query, setQuery] = useState('')
  const [tick, setTick] = useState(0)

  const records = useMemo(() => {
    void tick
    const all = listLibraryRecords()
    const q = query.trim().toLowerCase()
    if (!q) return all
    return all.filter((r) => {
      const e = r.extract
      const hay = [
        e.title,
        e.doi,
        e.venue,
        e.contribution,
        r.sourceFilename,
        ...(e.authors || []),
        ...(e.methods || []),
        ...(e.datasets || []),
        ...(e.metrics || []),
        ...(e.keywords || []),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [query, tick])

  const refresh = () => setTick((n) => n + 1)

  const handleDelete = (id: string) => {
    if (!confirm('确定删除这条文献记录？')) return
    deleteLibraryRecord(id)
    refresh()
  }

  const handleClear = () => {
    if (!confirm('确定清空本地文献库？此操作不可恢复。')) return
    clearLibrary()
    refresh()
  }

  const handleExportJson = () => {
    downloadExtractJson(
      records.map((r) => r.extract),
      'literature-library.json',
    )
  }

  const handleExportCsv = () => {
    downloadLibraryCsv(records)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">本地文献库</h2>
          <p className="text-sm text-slate-500 mt-1">
            数据保存在浏览器 localStorage，可批量导出 JSON / CSV 建综述表。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="text-sm px-3 py-2 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              ← 返回工作台
            </button>
          )}
          <button
            type="button"
            onClick={handleExportJson}
            disabled={!records.length}
            className="text-sm px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
          >
            导出 JSON
          </button>
          <button
            type="button"
            onClick={handleExportCsv}
            disabled={!records.length}
            className="text-sm px-3 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            导出 CSV
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={!listLibraryRecords().length}
            className="text-sm px-3 py-2 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            清空
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索标题、作者、方法、数据集..."
          className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
        />
        <span className="text-xs text-slate-400 whitespace-nowrap">{records.length} 条</span>
      </div>

      {!records.length ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center text-sm text-slate-400">
          暂无记录。请先在工作台使用「信息抽取」，再点击「保存到文献库」。
        </div>
      ) : (
        <div className="space-y-3">
          {records.map((r) => (
            <LibraryCard key={r.id} record={r} onDelete={() => handleDelete(r.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function LibraryCard({ record, onDelete }: { record: LibraryRecord; onDelete: () => void }) {
  const e = record.extract
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            {e.title || '（无标题）'}
          </h3>
          <p className="text-xs text-slate-500 mt-1">
            {(e.authors || []).slice(0, 4).join(', ') || '作者未知'}
            {e.year ? ` · ${e.year}` : ''}
            {e.venue ? ` · ${e.venue}` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="text-xs text-slate-400 hover:text-red-600 shrink-0"
        >
          删除
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 text-[11px]">
        {e.doi && (
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">DOI: {e.doi}</span>
        )}
        {record.sourceFilename && (
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {record.sourceFilename}
          </span>
        )}
        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
          {new Date(record.createdAt).toLocaleString()}
        </span>
      </div>

      {(e.methods.length > 0 || e.datasets.length > 0 || e.metrics.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-slate-600 pt-1">
          <div>
            <span className="text-slate-400">方法：</span>
            {e.methods.join('；') || '—'}
          </div>
          <div>
            <span className="text-slate-400">数据：</span>
            {e.datasets.join('；') || '—'}
          </div>
          <div>
            <span className="text-slate-400">指标：</span>
            {e.metrics.join('；') || '—'}
          </div>
        </div>
      )}

      {e.contribution && (
        <p className="text-xs text-slate-600 leading-relaxed">{e.contribution}</p>
      )}
    </article>
  )
}
