import { useState } from 'react'
import { moduleLabel } from '../lib/modules'

const input =
  'rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm transition focus:border-violet-400 focus:ring-4 focus:ring-violet-100 focus:outline-none'

// Edit the question plan before the interview starts. onSave(plan) persists it.
export default function PlanEditor({ plan, duration, onSave }) {
  const [sections, setSections] = useState(plan.sections)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const total = sections.reduce((sum, s) => sum + (Number(s.minutes) || 0), 0)

  function update(i, patch) {
    setSections((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)))
    setDirty(true)
  }

  function setQuestion(i, qi, text) {
    update(i, { questions: sections[i].questions.map((q, k) => (k === qi ? text : q)) })
  }

  async function save() {
    setError('')
    setBusy(true)
    try {
      await onSave({
        sections: sections.map((s) => ({ ...s, minutes: Number(s.minutes) })),
        reserve: plan.reserve,
      })
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {sections.map((s, i) => (
        <section key={i} className="card border-l-4 border-l-violet-400 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label={`Section ${i + 1} name`}
              value={s.name}
              onChange={(e) => update(i, { name: e.target.value })}
              className={`${input} font-medium`}
            />
            <input
              aria-label={`Section ${i + 1} minutes`}
              type="number"
              min={1}
              max={60}
              value={s.minutes}
              onChange={(e) => update(i, { minutes: e.target.value })}
              className={`${input} w-16`}
            />
            <span className="text-sm text-slate-500">min</span>
            <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-700">
              {moduleLabel(s.module)}
            </span>
          </div>
          {s.scenario && (
            <dl className="mt-3 grid gap-1 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200 sm:grid-cols-[auto_1fr] sm:gap-x-3">
              <dt className="font-medium">Interviewer plays</dt>
              <dd>{s.scenario.character}</dd>
              {s.scenario.setting && (
                <>
                  <dt className="font-medium">Setting</dt>
                  <dd>{s.scenario.setting}</dd>
                </>
              )}
              <dt className="font-medium">Your goal</dt>
              <dd>{s.scenario.goal}</dd>
            </dl>
          )}
          {s.scenario && (
            <p className="mt-2 text-xs text-slate-500">
              The question below is the character's opening line; the conversation continues
              live.
            </p>
          )}
          <ol className="mt-3 space-y-2">
            {s.questions.map((q, qi) => (
              <li key={qi} className="flex gap-2">
                <textarea
                  aria-label={`Section ${i + 1} question ${qi + 1}`}
                  rows={2}
                  value={q}
                  onChange={(e) => setQuestion(i, qi, e.target.value)}
                  className={`${input} flex-1`}
                />
                {s.questions.length > 1 && (
                  <button
                    type="button"
                    aria-label={`Remove section ${i + 1} question ${qi + 1}`}
                    onClick={() => update(i, { questions: s.questions.filter((_, k) => k !== qi) })}
                    className="text-sm text-slate-500 hover:text-red-600"
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ol>
          <button
            type="button"
            onClick={() => update(i, { questions: [...s.questions, ''] })}
            className="mt-3 text-sm font-semibold text-violet-700 hover:underline"
          >
            + Add question
          </button>
        </section>
      ))}

      <p className={`text-sm ${total === duration ? 'text-slate-600' : 'text-red-600'}`}>
        Sections total {total} of {duration} minutes.
      </p>
      {plan.reserve.length > 0 && (
        <p className="text-sm text-slate-500">
          Plus {plan.reserve.length} bonus question{plan.reserve.length > 1 ? 's' : ''} if you
          finish early.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {dirty && (
        <button
          type="button"
          onClick={save}
          disabled={busy || total !== duration}
          className="btn-secondary"
        >
          {busy ? 'Saving…' : 'Save changes'}
        </button>
      )}
    </div>
  )
}
