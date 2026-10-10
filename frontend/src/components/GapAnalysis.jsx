import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const STATUS = {
  covered: ['✓', 'Covered', 'bg-emerald-100 text-emerald-700'],
  partial: ['~', 'Partly', 'bg-accent-100 text-accent-700'],
  missing: ['✗', 'Not on your résumé', 'bg-brand-100 text-brand-700'],
}

// Résumé vs job: what's covered, and the questions the gaps will trigger.
export default function GapAnalysis({ resumeId, jdId }) {
  const [gaps, setGaps] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setGaps(null)
    setError('')
  }, [resumeId, jdId])

  async function run() {
    setError('')
    setBusy(true)
    try {
      setGaps((await api(`/documents/${jdId}/gaps`, { method: 'POST', body: { resume_id: resumeId } })).gaps)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!gaps) {
    return (
      <div className="card flex flex-wrap items-center gap-4 p-5">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">🧩 </span>Résumé gap analysis
          </h2>
          <p className="text-sm text-slate-500">
            See which requirements your résumé covers, and the questions the gaps will trigger.
          </p>
        </div>
        <button type="button" onClick={run} disabled={busy} className="btn-secondary">
          {busy ? 'Comparing…' : 'Check my résumé against this job'}
        </button>
        {error && (
          <p role="alert" className="basis-full text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    )
  }

  return (
    <section className="card space-y-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">🧩 </span>Résumé gap analysis
          </h2>
          <p className="mt-1 text-sm text-slate-600">{gaps.summary}</p>
        </div>
        <ul className="flex gap-2 text-xs">
          {['covered', 'partial', 'missing'].map((k) => (
            <li key={k} className={`chip ${STATUS[k][2]}`}>
              {gaps.counts[k]} {STATUS[k][1].toLowerCase()}
            </li>
          ))}
        </ul>
      </div>
      <ul className="divide-y divide-[#f3ebe1]">
        {gaps.requirements.map((r) => {
          const [icon, label, tone] = STATUS[r.status]
          return (
            <li key={r.requirement} className="flex gap-3 py-3 text-sm">
              <span aria-label={label} className={`grid h-6 w-6 shrink-0 place-items-center rounded-full font-bold ${tone}`}>
                {icon}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-ink">{r.requirement}</p>
                {r.evidence && (
                  <p className="text-slate-500">
                    Your résumé: <q className="rounded bg-emerald-50 px-1 text-emerald-800 italic">{r.evidence}</q>
                  </p>
                )}
                {r.likely_question && (
                  <p className="mt-0.5 text-slate-600">
                    <span className="font-semibold">Be ready for:</span> {r.likely_question}
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <p className="text-xs text-slate-500">
        “Not on your résumé” only means it isn't listed: you may still have it, so prepare an example.
      </p>
    </section>
  )
}
