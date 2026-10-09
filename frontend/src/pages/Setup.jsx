import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DocumentInput from '../components/DocumentInput'
import { api } from '../lib/api'
import { answerModePref, canRecord, setAnswerModePref } from '../lib/recording'
import { voicePref } from '../lib/voice'

const DURATIONS = [10, 30, 45, 60]

// Role detection for the chosen job description, and the interview types that fit.
function useJobAnalysis(jdId) {
  const [state, setState] = useState({ status: 'idle' })
  useEffect(() => {
    if (!jdId) {
      setState({ status: 'idle' })
      return
    }
    let live = true
    setState({ status: 'loading' })
    api(`/documents/${jdId}/analysis`, { method: 'POST' })
      .then((data) => live && setState({ status: 'ready', ...data }))
      .catch((err) => live && setState({ status: 'error', error: err.message }))
    return () => {
      live = false
    }
  }, [jdId])
  return state
}

function Choice({ name, options, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={name}>
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          onClick={() => onChange(key)}
          className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
            value === key
              ? 'border-transparent bg-gradient-to-r from-brand-600 to-accent-500 text-white shadow-md shadow-brand-500/25'
              : 'border-slate-200 bg-white text-slate-700 hover:border-brand-300 hover:text-brand-700'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

export default function Setup() {
  const navigate = useNavigate()
  const [resumeId, setResumeId] = useState(null)
  const [jdId, setJdId] = useState(null)
  const [duration, setDuration] = useState(10)
  const [custom, setCustom] = useState(false)
  const [difficulty, setDifficulty] = useState('mid')
  const [persona, setPersona] = useState('neutral')
  const [focus, setFocus] = useState('mixed')
  const [startNow, setStartNow] = useState(false)
  const [answerMode, setAnswerMode] = useState(answerModePref)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const job = useJobAnalysis(jdId)
  const offered = job.status === 'ready' ? job.modules : []
  // A type that fit the previous job description may not fit this one.
  const chosen = focus === 'mixed' || offered.some((m) => m.name === focus) ? focus : 'mixed'

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { session } = await api('/sessions', {
        method: 'POST',
        body: {
          resume_id: resumeId,
          jd_id: jdId,
          duration_min: duration,
          difficulty,
          persona,
          focus: chosen,
        },
      })
      setAnswerModePref(answerMode)
      if (!startNow) {
        navigate(`/interview/${session.id}`)
        return
      }
      // Skip the plan screen: start now and greet on the interview page.
      try {
        const fire = session.voice?.provider === 'fire' && voicePref()
        const data = await api(`/sessions/${session.id}/start`, {
          method: 'POST',
          ...(fire ? { body: { speak: true } } : {}),
        })
        navigate(`/interview/${session.id}`, {
          state: { greeting: { segments: data.session.transcript[0]?.segments, clips: data.speech } },
        })
      } catch {
        // e.g. a daily cap: the plan screen shows the reason when they press Start.
        navigate(`/interview/${session.id}`)
      }
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <header>
        <p className="eyebrow">{startNow ? 'Set up your interview' : 'Step 1 of 2'}</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">New interview</h1>
        <p className="mt-2 text-slate-600">
          Add your résumé and the job you're going for, then choose how you want to practice.
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <DocumentInput kind="resume" value={resumeId} onChange={setResumeId} />
        <DocumentInput kind="job_description" value={jdId} onChange={setJdId} />
      </div>

      {job.status === 'loading' && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          Reading the job description…
        </p>
      )}
      {job.status === 'error' && (
        <p role="alert" className="text-sm text-red-600">
          {job.error}
        </p>
      )}
      {job.status === 'ready' && (
        <section className="card space-y-3 p-5">
          <h2 className="font-semibold text-slate-900">Interview type</h2>
          <p className="text-sm text-slate-600">
            {job.analysis.role_title} · {job.analysis.field}
            {job.analysis.competencies.length > 0 &&
              ` · ${job.analysis.competencies.map((c) => c.name).join(', ')}`}
          </p>
          <Choice
            name="Interview type"
            options={[
              ['mixed', 'Full mixed loop'],
              ...offered.map((m) => [m.name, m.label]),
            ]}
            value={chosen}
            onChange={setFocus}
          />
          <p className="text-sm text-slate-500">
            {chosen === 'mixed'
              ? 'A realistic loop mixing the formats that fit this job.'
              : offered.find((m) => m.name === chosen)?.blurb}
          </p>
        </section>
      )}

      <div className="card grid gap-6 p-5 md:grid-cols-3">
        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Length</h2>
          <Choice
            name="Length"
            options={[...DURATIONS.map((d) => [d, `${d} min`]), ['custom', 'Custom']]}
            value={custom ? 'custom' : duration}
            onChange={(v) => {
              setCustom(v === 'custom')
              if (v !== 'custom') setDuration(v)
            }}
          />
          {custom && (
            <label className="flex items-center gap-3 text-sm">
              <input
                type="range"
                min={5}
                max={60}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                aria-label="Custom length in minutes"
                className="accent-brand-600"
              />
              <span>{duration} minutes</span>
            </label>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Difficulty</h2>
          <Choice
            name="Difficulty"
            options={[
              ['entry', 'Entry'],
              ['mid', 'Mid'],
              ['senior', 'Senior'],
            ]}
            value={difficulty}
            onChange={setDifficulty}
          />
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Interviewer</h2>
          <Choice
            name="Interviewer"
            options={[
              ['friendly', 'Friendly'],
              ['neutral', 'Neutral'],
              ['tough', 'Tough'],
            ]}
            value={persona}
            onChange={setPersona}
          />
        </section>
      </div>

      <div className="card grid gap-6 p-5 md:grid-cols-2">
        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Before you start</h2>
          <Choice
            name="Questions"
            options={[
              ['review', 'Review the questions first'],
              ['start', 'Start right away'],
            ]}
            value={startNow ? 'start' : 'review'}
            onChange={(v) => setStartNow(v === 'start')}
          />
          <p className="text-sm text-slate-500">
            {startNow
              ? 'The questions stay a surprise, like a real interview.'
              : 'See the plan, edit any question or the minutes, then start.'}
          </p>
        </section>
        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Answer by</h2>
          <Choice
            name="Answer by"
            options={[...(canRecord() ? [['voice', '🎙️ Speaking']] : []), ['text', '⌨️ Typing']]}
            value={answerMode}
            onChange={setAnswerMode}
          />
          <p className="text-sm text-slate-500">
            {answerMode === 'voice'
              ? 'Recording starts by itself when the interviewer finishes speaking.'
              : 'Type each answer. You can switch to speaking any time.'}
          </p>
        </section>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !resumeId || !jdId || job.status !== 'ready'}
        className="btn-primary"
      >
        {busy
          ? startNow
            ? 'Getting your interview ready…'
            : 'Building your interview plan…'
          : startNow
            ? 'Start my interview'
            : 'Build my interview plan'}
      </button>
      {busy && (
        <p className="text-sm text-slate-500">
          Reading the job description and your résumé; this takes a few seconds.
        </p>
      )}
    </form>
  )
}
