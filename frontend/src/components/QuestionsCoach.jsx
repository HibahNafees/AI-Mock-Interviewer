import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const TOPIC = { role: 'The role', team: 'The team', growth: 'Growth', process: 'How they work', company: 'The company' }

// Smart questions to ask them at the end of the interview, for this job.
export default function QuestionsCoach({ jdId }) {
  const [coach, setCoach] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setCoach(null)
    setError('')
  }, [jdId])

  async function run() {
    setError('')
    setBusy(true)
    try {
      setCoach((await api(`/documents/${jdId}/questions-to-ask`, { method: 'POST' })).coach)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">💬 </span>Questions to ask them
          </h2>
          <p className="text-sm text-slate-500">
            Every interview ends with “Do you have any questions for me?”. Have good ones ready.
          </p>
        </div>
        {!coach && (
          <button type="button" onClick={run} disabled={busy} className="btn-secondary">
            {busy ? 'Thinking…' : 'Suggest questions'}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {coach && (
        <>
          <ul className="space-y-2">
            {coach.questions.map((q) => (
              <li key={q.question} className="text-sm">
                <span className="chip mr-2 bg-navy-50 text-navy-700">{TOPIC[q.topic] ?? q.topic}</span>
                <span className="font-medium text-ink">{q.question}</span>
                {q.why && <span className="block pl-1 text-slate-500">{q.why}</span>}
              </li>
            ))}
          </ul>
          {coach.avoid?.length > 0 && (
            <p className="rounded-xl bg-accent-50 p-3 text-sm text-accent-700 ring-1 ring-accent-200">
              <span className="font-semibold">Avoid:</span> {coach.avoid.join(' ')}
            </p>
          )}
        </>
      )}
    </section>
  )
}
