import type { TaskType } from '../types'

interface TaskTabProps {
  active: TaskType
  onChange: (task: TaskType) => void
}

const TABS: { id: TaskType; label: string; icon: string; desc: string }[] = [
  { id: 'summarize', label: '摘要提炼', icon: '📋', desc: '结构化提炼文献要点' },
  { id: 'translate', label: '学术翻译', icon: '🌐', desc: '中英文学术互译' },
  { id: 'polish', label: '润色优化', icon: '✨', desc: '提升表达与学术规范' },
]

function tabClassName(isActive: boolean): string {
  const base = 'rounded-xl border p-4 text-left transition-all'
  return isActive
    ? `${base} border-indigo-500 bg-indigo-50 shadow-sm ring-1 ring-indigo-500/20`
    : `${base} border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50`
}

export default function TaskTabs({ active, onChange }: TaskTabProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {TABS.map((tab) => {
        const isActive = active === tab.id
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={tabClassName(isActive)}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xl">{tab.icon}</span>
              <span className={`font-semibold ${isActive ? 'text-indigo-700' : 'text-slate-800'}`}>
                {tab.label}
              </span>
            </div>
            <p className="text-sm text-slate-500">{tab.desc}</p>
          </button>
        )
      })}
    </div>
  )
}
