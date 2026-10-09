import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const LABELS = { resume: 'Your résumé', job_description: 'Job description' }

// Pick a saved document, upload a PDF/.txt, or paste text. Calls onChange(docId).
export default function DocumentInput({ kind, value, onChange }) {
  const [docs, setDocs] = useState([])
  const [mode, setMode] = useState('paste')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/documents?kind=${kind}`)
      .then((data) => {
        setDocs(data.documents)
        if (data.documents.length) {
          setMode('saved')
          onChange(data.documents[0].id)
        }
      })
      .catch(() => {})
    // Load once per kind; onChange is a fresh closure each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  function added(doc) {
    setDocs((d) => [doc, ...d])
    setMode('saved')
    setText('')
    onChange(doc.id)
  }

  async function save(body) {
    setError('')
    setBusy(true)
    try {
      added((await api('/documents', { method: 'POST', body })).document)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function upload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append('kind', kind)
    form.append('file', file)
    save(form)
    e.target.value = ''
  }

  const tabs = [
    ...(docs.length ? [['saved', 'Saved']] : []),
    ['paste', 'Paste'],
    ['upload', 'Upload file'],
  ]

  return (
    <fieldset className="rounded-lg border border-slate-200 bg-white p-4">
      <legend className="px-1 font-medium">{LABELS[kind]}</legend>
      <div className="mb-3 flex gap-2 text-sm" role="tablist">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={mode === key}
            onClick={() => setMode(key)}
            className={`rounded-md px-3 py-1 ${
              mode === key ? 'bg-indigo-100 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'saved' && (
        <select
          aria-label={`Saved ${LABELS[kind].toLowerCase()}`}
          value={value ?? ''}
          onChange={(e) => onChange(Number(e.target.value))}
          className="block w-full rounded-md border border-slate-300 px-3 py-2"
        >
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
            </option>
          ))}
        </select>
      )}

      {mode === 'paste' && (
        <div className="space-y-2">
          <textarea
            aria-label={`Paste ${LABELS[kind].toLowerCase()}`}
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={kind === 'resume' ? 'Paste your résumé text…' : 'Paste the job posting…'}
            className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            disabled={busy || text.trim().length < 50}
            onClick={() => save({ kind, text })}
            className="rounded-md border border-indigo-600 px-3 py-1 text-sm text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Use this text'}
          </button>
        </div>
      )}

      {mode === 'upload' && (
        <label className="block text-sm text-slate-600">
          PDF or .txt, up to 5 MB. Only the text is kept, for 30 days.
          <input
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain"
            onChange={upload}
            disabled={busy}
            className="mt-2 block text-sm"
          />
        </label>
      )}

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </fieldset>
  )
}
