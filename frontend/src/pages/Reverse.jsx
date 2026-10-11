import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { IconTile, Mascot } from '../components/Art'
import Recorder from '../components/Recorder'
import { api } from '../lib/api'
import { canRecord } from '../lib/recording'

const PROFILES = [
  ['surprise', 'Surprise me'],
  ['strong', 'Strong'],
  ['average', 'Average'],
  ['weak', 'Weak'],
  ['exaggerating', 'Exaggerates their résumé'],
]
const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }
// Matches the backend's limits for a reverse interview.
const MIN_MINUTES = 5
const MAX_MINUTES = 30

function minutesLeft(v, now) {
  if (!v.started_at) return null
  const end = new Date(v.started_at).getTime() + v.duration_min * 60_000
  return Math.max(0, Math.ceil((end - now) / 60_000))
}

function Pills({ name, options, value, onChange }) {
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
              ? 'border-transparent bg-gradient-to-r from-brand-600 to-accent-500 text-white shadow-md'
              : 'border-slate-200 bg-surface text-slate-700 hover:border-brand-300'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

export function ReverseSetup() {
  const navigate = useNavigate()
  const [jds, setJds] = useState(null)
  const [jdId, setJdId] = useState('')
  const [profile, setProfile] = useState('surprise')
  const [duration, setDuration] = useState(10)
  const [custom, setCustom] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/documents?kind=job_description')
      .then((d) => {
        setJds(d.documents ?? [])
        if (d.documents?.length) setJdId(String(d.documents[0].id))
      })
      .catch(() => setJds([]))
  }, [])

  async function start(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { reverse } = await api('/reverse', {
        method: 'POST',
        body: { jd_id: Number(jdId), profile, duration_min: duration },
      })
      navigate(`/reverse/${reverse.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Reverse mode</p>
          <h1 className="mt-1 text-3xl font-extrabold">You're the interviewer</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            The AI plays a candidate for the job, with a hidden profile. Ask your questions,
            decide hire or no hire, then see who they really were and how well you interviewed.
            Great for hearing weak answers from the other side, or for practicing hiring.
          </p>
        </div>
        <IconTile tone="navy" className="hidden h-14 w-14 text-2xl sm:grid">
          🔄
        </IconTile>
      </header>
      {jds && jds.length === 0 ? (
        <div className="card p-6 text-sm text-slate-600">
          Add a job description first (on{' '}
          <Link to="/setup" className="font-semibold text-brand-700 underline">
            New interview
          </Link>
          ), then come back to interview a candidate for it.
        </div>
      ) : (
        <form onSubmit={start} className="card space-y-5 p-6">
          <label className="block text-sm font-medium text-slate-700">
            Job they're applying for
            <select value={jdId} onChange={(e) => setJdId(e.target.value)} className="field mt-1">
              {(jds ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}
                </option>
              ))}
            </select>
          </label>
          <div className="space-y-2">
            <p className="text-sm font-medium text-slate-700">Candidate (kept secret until your decision)</p>
            <Pills name="Candidate" options={PROFILES} value={profile} onChange={setProfile} />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium text-slate-700">Length</p>
            <Pills
              name="Length"
              options={[[10, '10 min'], [20, '20 min'], ['custom', 'Custom']]}
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
                  min={MIN_MINUTES}
                  max={MAX_MINUTES}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  aria-label="Custom length in minutes"
                  className="accent-brand-600"
                />
                <span className="font-semibold tabular-nums">{duration} minutes</span>
              </label>
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy || !jdId} className="btn-primary">
            {busy ? 'Your candidate is on their way…' : 'Meet the candidate'}
          </button>
        </form>
      )}
    </section>
  )
}

function Reveal({ v }) {
  const { profile, hidden, result } = v.reveal
  const sound = result.decision_matches
  return (
    <div className="space-y-4">
      <div className={`rounded-3xl p-6 text-white ${sound ? 'bg-gradient-to-br from-emerald-500 to-teal-600' : 'bg-gradient-to-br from-brand-500 to-accent-500'}`}>
        <p className="text-sm font-semibold tracking-wider text-white/80 uppercase">The reveal</p>
        <h2 className="mt-1 text-2xl font-extrabold text-white">
          {v.candidate.name} was {profile === 'exaggerating' ? 'exaggerating their résumé' : `a ${profile} candidate`}
        </h2>
        <p className="mt-2 text-white/90">
          You said <span className="font-bold">{result.decision === 'hire' ? 'hire' : 'no hire'}</span>.{' '}
          {result.expected === 'either'
            ? 'This one could go either way: your reasons are what count.'
            : sound
              ? 'That matches what a careful interviewer would decide.'
              : `A careful interviewer would most likely say ${result.expected === 'hire' ? 'hire' : 'no hire'}.`}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {[
          ['Your judgment', result.judgment],
          ['Your questions', result.questioning],
        ].map(([label, s]) => (
          <div key={label} className="card p-5">
            <p className="text-sm font-semibold text-slate-500">{label}</p>
            <p className="font-display text-3xl font-extrabold text-ink">{s.score} / 5</p>
            <p className="mt-1 text-sm text-slate-600">{s.comment}</p>
          </div>
        ))}
      </div>
      <div className="card grid gap-5 p-6 md:grid-cols-2">
        <div>
          <h3 className="font-bold">What was really true</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {hidden.truths.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          {hidden.exaggerations?.length > 0 && (
            <>
              <h3 className="mt-4 font-bold">Exaggerated on the résumé</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-brand-800">
                {hidden.exaggerations.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div className="space-y-4">
          {result.missed_signals?.length > 0 && (
            <div>
              <h3 className="font-bold">Signals you missed</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {result.missed_signals.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          {result.good_moves?.length > 0 && (
            <div>
              <h3 className="font-bold">What you did well</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-emerald-800">
                {result.good_moves.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          {result.unfair_questions?.length > 0 && (
            <p className="rounded-xl bg-brand-50 p-3 text-sm text-brand-800 ring-1 ring-brand-200">
              <span className="font-bold">Avoid in real interviews:</span> “{result.unfair_questions.join('” · “')}”
              Questions about personal matters aren't job-related and can be unlawful.
            </p>
          )}
        </div>
      </div>
      {result.question_feedback?.length > 0 && (
        <div className="card p-6">
          <h3 className="font-bold">Question by question</h3>
          <ol className="mt-3 space-y-2 text-sm">
            {result.question_feedback.map((q, i) => (
              <li key={i} className="flex gap-3">
                <span className="chip shrink-0 bg-navy-50 text-navy-700 tabular-nums">{q.score}/5</span>
                <span>
                  <span className="font-medium text-ink">{q.question}</span>
                  <span className="block text-slate-500">{q.comment}</span>
                </span>
              </li>
            ))}
          </ol>
          {result.tips?.length > 0 && (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {result.tips.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <Link to="/reverse" className="btn-secondary">
        Interview another candidate
      </Link>
    </div>
  )
}

export default function Reverse() {
  const { id } = useParams()
  const [v, setV] = useState(null)
  const [text, setText] = useState('')
  const [mode, setMode] = useState('text')
  const [phase, setPhase] = useState('idle')
  const [deciding, setDeciding] = useState(false)
  const [decision, setDecision] = useState('hire')
  const [reasons, setReasons] = useState('')
  const [error, setError] = useState('')
  const bottom = useRef(null)
  const busy = phase !== 'idle'
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    api(`/reverse/${id}`)
      .then((d) => setV(d.reverse))
      .catch((err) => setError(err.message))
  }, [id])

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [v?.transcript.length])

  async function ask(question, input_mode) {
    setError('')
    setPhase('thinking')
    try {
      setV((await api(`/reverse/${id}/ask`, { method: 'POST', body: { text: question, input_mode } })).reverse)
      setText('')
    } catch (err) {
      setError(err.message)
      setText(question)
    } finally {
      setPhase('idle')
    }
  }

  async function onRecorded(blob) {
    setError('')
    setPhase('transcribing')
    const form = new FormData()
    form.append('audio', blob, `question.${EXT[blob.type.split(';')[0]] ?? 'webm'}`)
    try {
      const { text: heard } = await api(`/sessions/${id}/transcribe`, { method: 'POST', body: form })
      await ask(heard, 'voice')
    } catch (err) {
      setError(err.message)
      setPhase('idle')
    }
  }

  async function decide(e) {
    e.preventDefault()
    setError('')
    setPhase('judging')
    try {
      setV((await api(`/reverse/${id}/decide`, { method: 'POST', body: { decision, reasons } })).reverse)
    } catch (err) {
      setError(err.message)
    } finally {
      setPhase('idle')
    }
  }

  if (!v) return error ? <p role="alert" className="text-red-600">{error}</p> : <p className="text-slate-500">Loading…</p>
  const asked = v.transcript.length
  const open = v.status === 'active'
  const left = open ? minutesLeft(v, now) : null

  return (
    <section className="space-y-6">
      <div className="card flex flex-wrap items-start gap-5 p-6">
        <span
          aria-hidden="true"
          className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent-300 to-accent-500 text-2xl font-extrabold text-white"
        >
          {v.candidate.name?.[0]}
        </span>
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Candidate for {v.role_title}</p>
          <h1 className="text-2xl font-extrabold">{v.candidate.name}</h1>
          <p className="text-slate-600">{v.candidate.headline}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {v.candidate.resume.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
        {open && (
          <div className="flex flex-col items-end gap-2">
            <p className="chip bg-navy-50 text-navy-700">
              {asked} / {v.max_questions} questions
            </p>
            {left != null && (
              <p
                aria-label="Time left"
                className={`chip ${left <= 1 ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600'}`}
              >
                {left > 0 ? `${left} min left of ${v.duration_min}` : "Time's up"}
              </p>
            )}
          </div>
        )}
      </div>

      {asked === 0 && open && (
        <div className="flex items-center gap-4 rounded-2xl bg-sand p-4 text-sm text-slate-700">
          <Mascot className="h-12 w-12 shrink-0" />
          <p>
            Start with an opener, then probe: ask what they <em>personally</em> did, for numbers,
            and how they'd handle a real situation in this job. Watch for claims that don't hold up.
          </p>
        </div>
      )}

      <ol className="space-y-4">
        {v.transcript.map((t, i) => (
          <li key={i} className="space-y-3">
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-md bg-night p-4 text-white">
              <p className="mb-1 text-xs font-semibold tracking-wide text-white/80 uppercase">You (interviewer)</p>
              <p>{t.question}</p>
            </div>
            <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-accent-50 p-4 ring-1 ring-accent-200">
              <p className="mb-1 text-xs font-semibold tracking-wide text-accent-700 uppercase">{v.candidate.name}</p>
              <p className="text-slate-800">{t.answer}</p>
            </div>
          </li>
        ))}
      </ol>
      {busy && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          {phase === 'transcribing' ? 'Listening back…' : phase === 'judging' ? 'Reviewing your interview…' : `${v.candidate.name} is answering…`}
        </p>
      )}
      <div ref={bottom} />

      {open && !deciding && left === 0 && (
        <p className="rounded-2xl bg-accent-50 p-4 text-sm text-accent-700 ring-1 ring-accent-200">
          <span className="font-bold">Time's up.</span> In a real interview you'd wrap up now:
          make your decision below (you can still ask one last question).
        </p>
      )}
      {open && !deciding && (
        <div className="card space-y-3 p-5">
          {mode === 'voice' ? (
            <Recorder onRecorded={onRecorded} disabled={busy || asked >= v.max_questions} />
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (text.trim()) ask(text.trim(), 'text')
              }}
              className="space-y-2"
            >
              <textarea
                aria-label="Your question"
                rows={3}
                value={text}
                disabled={busy}
                onChange={(e) => setText(e.target.value)}
                placeholder="Ask your next question…"
                className="field"
              />
              <button type="submit" disabled={busy || !text.trim() || asked >= v.max_questions} className="btn-primary">
                Ask
              </button>
            </form>
          )}
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-slate-100 pt-3">
            {canRecord() && (
              <button type="button" disabled={busy} onClick={() => setMode((m) => (m === 'voice' ? 'text' : 'voice'))} className="btn-link">
                {mode === 'voice' ? 'Type instead' : 'Speak instead'}
              </button>
            )}
            <button type="button" disabled={busy || asked === 0} onClick={() => setDeciding(true)} className="btn-link">
              <span aria-hidden="true">⚖️ </span>Make your decision
            </button>
          </div>
        </div>
      )}

      {open && deciding && (
        <form onSubmit={decide} className="card space-y-4 p-6">
          <h2 className="text-lg font-bold">Your decision</h2>
          <Pills
            name="Decision"
            options={[
              ['hire', 'Hire'],
              ['no_hire', 'No hire'],
            ]}
            value={decision}
            onChange={setDecision}
          />
          <label className="block text-sm font-medium text-slate-700">
            Why? Cite what they said.
            <textarea rows={3} value={reasons} onChange={(e) => setReasons(e.target.value)} className="field mt-1" />
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={busy || reasons.trim().length < 3} className="btn-primary">
              Reveal the candidate
            </button>
            <button type="button" onClick={() => setDeciding(false)} className="btn-link">
              Keep interviewing
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {v.reveal && <Reveal v={v} />}
    </section>
  )
}
