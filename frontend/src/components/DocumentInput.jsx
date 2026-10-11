import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const LABELS = { resume: 'Your résumé', job_description: 'Job description' }
const ICONS = { resume: '📄', job_description: '💼' }

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

  const [dragging, setDragging] = useState(false)

  function send(file) {
    if (!file) return
    const form = new FormData()
    form.append('kind', kind)
    form.append('file', file)
    save(form)
  }

  function upload(e) {
    send(e.target.files?.[0])
    e.target.value = ''
  }

  function drop(e) {
    e.preventDefault()
    setDragging(false)
    if (!busy) send(e.dataTransfer.files?.[0])
  }

  async function remove() {
    const doc = docs.find((d) => d.id === value)
    if (!doc) return
    const what = kind === 'resume' ? 'résumé' : 'job posting'
    if (!window.confirm(`Delete the saved ${what} "${doc.title}"? Past interview reports stay.`)) return
    setError('')
    setBusy(true)
    try {
      await api(`/documents/${doc.id}`, { method: 'DELETE' })
      const rest = docs.filter((d) => d.id !== doc.id)
      setDocs(rest)
      onChange(rest[0]?.id ?? null)
      if (!rest.length) setMode('paste')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const tabs = [
    ...(docs.length ? [['saved', 'Saved']] : []),
    ['paste', 'Paste'],
    ['upload', 'Upload file'],
  ]

  return (
    <fieldset className="card p-5">
      <legend className="sr-only">{LABELS[kind]}</legend>
      <p aria-hidden="true" className="mb-3 flex items-center gap-2 font-semibold text-slate-900">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-100 text-base">{ICONS[kind]}</span>
        {LABELS[kind]}
      </p>
      <div className="mb-4 inline-flex gap-1 rounded-full bg-slate-100 p-1 text-sm" role="tablist">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={mode === key}
            onClick={() => setMode(key)}
            className={`rounded-full px-3.5 py-1.5 font-medium transition ${
              mode === key ? 'bg-surface text-brand-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'saved' && (
        <div className="flex items-center gap-2">
          <select
            aria-label={`Saved ${LABELS[kind].toLowerCase()}`}
            value={value ?? ''}
            onChange={(e) => onChange(Number(e.target.value))}
            className="field min-w-0 flex-1"
          >
            {docs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={remove}
            disabled={busy || !value}
            aria-label={`Delete this saved ${kind === 'resume' ? 'résumé' : 'job posting'}`}
            className="btn-link shrink-0 text-sm hover:text-red-600"
          >
            Delete
          </button>
        </div>
      )}

      {mode === 'paste' && (
        <div className="space-y-2">
          <textarea
            aria-label={`Paste ${LABELS[kind].toLowerCase()}`}
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={kind === 'resume' ? 'Paste your résumé text…' : 'Paste the job posting…'}
            className="field text-sm"
          />
          <button
            type="button"
            disabled={busy || text.trim().length < 50}
            onClick={() => save({ kind, text })}
            className="btn-secondary"
          >
            {busy ? 'Saving…' : 'Use this text'}
          </button>
        </div>
      )}

      {mode === 'upload' && (
        // The whole box is the file picker (T-30: the bare input showed no button).
        <label
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
          className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition focus-within:ring-4 focus-within:ring-brand-100 ${
            dragging
              ? 'border-brand-500 bg-brand-50'
              : 'border-brand-200 bg-brand-50/40 hover:border-brand-400 hover:bg-brand-50'
          } ${busy ? 'pointer-events-none opacity-60' : ''}`}
        >
          <span
            aria-hidden="true"
            className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 text-white shadow-md shadow-brand-500/30"
          >
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="btn-primary px-4 py-2 text-sm">{busy ? 'Uploading…' : 'Choose file'}</span>
          <span className="text-sm text-slate-600">
            or drag it here · PDF or .txt, up to 5 MB
            <span className="block text-xs text-slate-500">Only the text is kept, for 30 days.</span>
          </span>
          <input
            type="file"
            aria-label={`Upload ${LABELS[kind].toLowerCase()} file`}
            accept=".pdf,.txt,.md,application/pdf,text/plain"
            onChange={upload}
            disabled={busy}
            className="sr-only"
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
