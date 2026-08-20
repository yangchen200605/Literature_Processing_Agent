import { useEffect, useState } from 'react'
import WorkspacePage from './pages/WorkspacePage'
import LibraryPage from './pages/LibraryPage'
import type { AppPage } from './types'

function pageFromHash(): AppPage {
  const hash = window.location.hash.replace(/^#\/?/, '')
  return hash === 'library' ? 'library' : 'workspace'
}

export default function App() {
  const [page, setPage] = useState<AppPage>(() => pageFromHash())

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (next: AppPage) => {
    window.location.hash = next === 'library' ? '#/library' : '#/'
    setPage(next)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
      <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">文献处理 Agent</h1>
            <p className="text-sm text-slate-500">
              摘要 · 信息抽取 · 翻译 · 润色 · 相似文献 · 本地文献库
            </p>
          </div>
          <nav className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1">
            <button
              type="button"
              onClick={() => go('workspace')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                page === 'workspace'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              工作台
            </button>
            <button
              type="button"
              onClick={() => go('library')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                page === 'library'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              文献库
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {page === 'workspace' ? (
          <WorkspacePage onOpenLibrary={() => go('library')} />
        ) : (
          <LibraryPage onBack={() => go('workspace')} />
        )}
      </main>
    </div>
  )
}
