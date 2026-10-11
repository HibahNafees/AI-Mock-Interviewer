import { lazy, Suspense, useState } from 'react'
import { useTheme } from '../lib/theme'

// Monaco loads on first use, so other pages stay small.
const Editor = lazy(() => import('../lib/monaco'))

const LANGUAGES = [
  ['python', 'Python'],
  ['javascript', 'JavaScript'],
  ['typescript', 'TypeScript'],
  ['java', 'Java'],
  ['csharp', 'C#'],
  ['cpp', 'C++'],
  ['go', 'Go'],
  ['ruby', 'Ruby'],
  ['kotlin', 'Kotlin'],
  ['swift', 'Swift'],
  ['sql', 'SQL'],
  ['plaintext', 'Plain text'],
]

function PlainBox({ value, onChange }) {
  return (
    <textarea
      aria-label="Your code"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      spellCheck={false}
      rows={14}
      className="field font-mono text-sm"
    />
  )
}

// The coding round's editor; its contents are sent with each answer.
export default function CodePad({ code, onChange }) {
  const theme = useTheme()
  const [plain, setPlain] = useState(false)
  const set = (content) => onChange({ ...code, content: content ?? '' })
  return (
    <section className="card space-y-3 p-4" aria-label="Code editor">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold text-ink">
          <span aria-hidden="true">⌨️ </span>Code editor
        </h2>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            Language
            <select
              value={code.language}
              onChange={(e) => onChange({ ...code, language: e.target.value })}
              className="rounded-xl border-2 border-field-line bg-surface px-2 py-1"
            >
              {LANGUAGES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => setPlain((p) => !p)} className="btn-link">
            {plain ? 'Use the code editor' : 'Use a plain text box'}
          </button>
        </div>
      </div>
      {plain ? (
        <PlainBox value={code.content} onChange={set} />
      ) : (
        <div className="overflow-hidden rounded-xl ring-1 ring-slate-200">
          <Suspense fallback={<PlainBox value={code.content} onChange={set} />}>
            <Editor
              height="320px"
              language={code.language}
              value={code.content}
              onChange={set}
              theme={theme === 'dark' ? 'vs-dark' : 'light'}
              loading={<p className="p-4 text-sm text-slate-500">Loading the editor…</p>}
              options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false, tabSize: 4 }}
            />
          </Suspense>
        </div>
      )}
      <p className="text-xs text-slate-500">
        Write your code here and talk it through in your answer. The interviewer sees your latest code each time
        you answer.
      </p>
    </section>
  )
}
