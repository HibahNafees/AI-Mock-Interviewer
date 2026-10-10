import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'

function Block({ title, children }) {
  return (
    <section className="break-inside-avoid">
      <h2 className="border-b border-slate-200 pb-1 text-sm font-bold tracking-wide text-brand-700 uppercase">{title}</h2>
      <div className="mt-2 text-sm text-slate-800">{children}</div>
    </section>
  )
}

// One printable page: their best stories, own numbers, weak spots, and questions.
export default function CheatSheet() {
  const { id } = useParams()
  const [sheet, setSheet] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/sessions/${id}/cheatsheet`)
      .then((d) => setSheet(d.sheet))
      .catch((err) => setError(err.message))
  }, [id])

  if (error) return <p role="alert" className="text-red-600">{error}</p>
  if (!sheet) return <p className="text-slate-500">Loading…</p>

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link to={`/report/${id}`} className="btn-link">
          ← Back to the report
        </Link>
        <button type="button" onClick={() => window.print()} className="btn-primary">
          Save as PDF / print
        </button>
      </div>
      <article className="card space-y-5 p-8 print:rounded-none print:border-0 print:p-0 print:shadow-none">
        <header>
          <p className="eyebrow">Interview cheat sheet</p>
          <h1 className="text-2xl font-extrabold">
            {sheet.role_title}
            {sheet.company ? ` · ${sheet.company}` : ''}
          </h1>
          <p className="text-xs text-slate-500">Built only from your own answers and stories. Glance at it right before you go in.</p>
        </header>
        <div className="grid gap-5 sm:grid-cols-2">
          <Block title="Stories to tell">
            {sheet.stories.length ? (
              <ol className="space-y-2">
                {sheet.stories.map((s) => (
                  <li key={s.title}>
                    <p className="font-semibold">{s.title}</p>
                    {s.action && <p className="text-slate-600">{s.action}</p>}
                    {s.result && <p className="text-slate-600">→ {s.result}</p>}
                    {s.fits.length > 0 && <p className="text-xs text-emerald-700">Shows: {s.fits.join(', ')}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-slate-500">No stories yet: they appear after your reports.</p>
            )}
          </Block>
          <Block title="Your numbers">
            {sheet.key_numbers.length ? (
              <ul className="list-disc space-y-1 pl-5">
                {sheet.key_numbers.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-500">No numbers in your answers yet: add a measured result to each story.</p>
            )}
          </Block>
          <Block title="Watch out for">
            <ul className="list-disc space-y-1 pl-5">
              {sheet.weak_spots.map((w) => (
                <li key={w.name}>
                  {w.name} <span className="text-slate-500">({w.score.toFixed(1)}/5 last time)</span>
                </li>
              ))}
              {sheet.takeaways.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </Block>
          <Block title="Be ready for">
            <ul className="list-disc space-y-1 pl-5">
              {sheet.likely_questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
            {sheet.questions_to_ask.length > 0 && (
              <>
                <p className="mt-3 font-semibold">Ask them</p>
                <ul className="list-disc space-y-1 pl-5">
                  {sheet.questions_to_ask.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </>
            )}
          </Block>
        </div>
      </article>
    </section>
  )
}
