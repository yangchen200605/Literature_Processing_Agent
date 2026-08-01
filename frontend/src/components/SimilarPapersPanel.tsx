import type { PaperItem, SimilarResponse } from '../types'

interface SimilarPapersPanelProps {
  data: SimilarResponse | null
  loading: boolean
  error: string | null
}

function PaperCard({ paper, badge }: { paper: PaperItem; badge?: string }) {
  const summary = paper.tldr || paper.abstract
  const authors =
    paper.authors.length > 0
      ? paper.authors.slice(0, 4).join(', ') + (paper.authors.length > 4 ? ' et al.' : '')
      : '作者未知'

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900 leading-snug">
          {paper.url ? (
            <a
              href={paper.url}
              target="_blank"
              rel="noreferrer"
              className="hover:text-indigo-700 hover:underline"
            >
              {paper.title}
            </a>
          ) : (
            paper.title
          )}
        </h3>
        {badge && (
          <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
            {badge}
          </span>
        )}
      </div>

      <p className="text-xs text-slate-500">
        {authors}
        {paper.year ? ` · ${paper.year}` : ''}
        {paper.venue ? ` · ${paper.venue}` : ''}
        {typeof paper.citation_count === 'number' ? ` · 引用 ${paper.citation_count}` : ''}
      </p>

      {summary && (
        <p className="text-sm text-slate-700 leading-relaxed line-clamp-4">{summary}</p>
      )}

      <div className="flex flex-wrap gap-3 pt-1">
        {paper.url && (
          <a
            href={paper.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
          >
            Semantic Scholar
          </a>
        )}
        {paper.doi && (
          <a
            href={`https://doi.org/${paper.doi}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
          >
            DOI
          </a>
        )}
        {paper.open_access_pdf && (
          <a
            href={paper.open_access_pdf}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-emerald-600 hover:text-emerald-800"
          >
            开放 PDF
          </a>
        )}
      </div>
    </article>
  )
}

export default function SimilarPapersPanel({ data, loading, error }: SimilarPapersPanelProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700">相似文献</label>
          {data?.via === 'mcp' && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 font-medium">
              via MCP
            </span>
          )}
        </div>
        {data?.query && (
          <span className="text-xs text-slate-400 truncate max-w-[55%]" title={data.query}>
            检索式：{data.query}
          </span>
        )}
      </div>

      <div className="flex-1 min-h-[280px] rounded-xl border border-slate-200 bg-slate-50/60 p-3 overflow-auto space-y-3">
        {loading && (
          <div className="flex flex-col items-center justify-center h-full min-h-[240px] gap-3 text-slate-500">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-sm">正在检索相似文献...</p>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && !error && data?.seed && (
          <PaperCard paper={data.seed} badge="种子论文" />
        )}

        {!loading &&
          !error &&
          data?.papers.map((paper) => <PaperCard key={paper.paper_id} paper={paper} />)}

        {!loading && !error && data && data.papers.length === 0 && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
            {data.message || '未找到相似文献'}
          </div>
        )}

        {!loading && !error && !data && (
          <div className="flex items-center justify-center h-full min-h-[240px] text-sm text-slate-400">
            输入标题、摘要或上传 PDF/Word 后开始检索
          </div>
        )}
      </div>
    </div>
  )
}
