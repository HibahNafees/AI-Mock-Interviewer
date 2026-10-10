import { useState } from 'react'
import { api } from '../lib/api'

// Read the company's public site; its "Why us?" questions can join the interview.
export default function CompanyResearch({ role, research, onChange, include, onIncludeChange }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run() {
    setError('')
    setBusy(true)
    try {
      const data = await api('/company/research', { method: 'POST', body: { url, role } })
      onChange(data.research)
      onIncludeChange(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!research) {
    return (
      <div className="card space-y-3 p-5">
        <div>
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">🏢 </span>Company research
          </h2>
          <p className="text-sm text-slate-500">
            Paste the company's website. We read its public page and prepare you for “Why us?” questions.
          </p>
        </div>
        {/* Not a nested <form>: this sits inside the setup form. */}
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              e.preventDefault() // don't submit the setup form
              if (url.trim() && !busy) run(e)
            }}
            placeholder="https://company.com/about"
            aria-label="Company website"
            className="field min-w-0 flex-1"
          />
          <button type="button" onClick={run} disabled={busy || !url.trim()} className="btn-secondary">
            {busy ? 'Reading the site…' : 'Research'}
          </button>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    )
  }

  return (
    <section className="card space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">🏢 </span>
            {research.company}
          </h2>
          <p className="mt-1 text-sm text-slate-600">{research.summary}</p>
        </div>
        <button type="button" onClick={() => onChange(null)} className="text-sm font-medium text-brand-700 hover:underline">
          Change
        </button>
      </div>
      {research.talking_points.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-ink">Worth mentioning</h3>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-600">
            {research.talking_points.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="text-sm font-semibold text-ink">“Why us?” questions</h3>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-600">
          {research.why_us_questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      </div>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={include}
          onChange={(e) => onIncludeChange(e.target.checked)}
          className="accent-brand-600"
        />
        Add a 2-minute “Why this company” section to my interview
      </label>
      <p className="text-xs text-slate-500">From the company's own website; check anything you plan to quote.</p>
    </section>
  )
}
