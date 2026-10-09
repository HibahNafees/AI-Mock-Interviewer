import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Recorder from '../components/Recorder'
import { api } from '../lib/api'
import { canRecord, MAX_ANSWER_MS } from '../lib/recording'

const POLL_MS = 2500
const VERDICT = {
  hire: ['Hire', 'bg-green-100 text-green-800'],
  'lean hire': ['Lean hire', 'bg-amber-100 text-amber-800'],
  'no hire': ['No hire', 'bg-red-100 text-red-800'],
}
const CHANGE = {
  added: 'bg-green-100 text-green-800',
  cut: 'bg-red-100 text-red-800',
  reframed: 'bg-sky-100 text-sky-800',
}
const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }

function fmtScore(s) {
  return s == null ? '–' : s.toFixed(1)
}

function fmtTime(sec) {
  if (sec == null) return '–'
  return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`
}

function scoreColor(s) {
  if (s == null) return 'bg-slate-100 text-slate-500'
  if (s >= 4) return 'bg-green-100 text-green-800'
  if (s >= 3) return 'bg-amber-100 text-amber-800'
  return 'bg-red-100 text-red-800'
}

function Score({ value, label = 'Score' }) {
  return (
    <span
      aria-label={`${label} ${fmtScore(value)} out of 5`}
      className={`inline-block rounded-md px-2 py-0.5 font-semibold tabular-nums ${scoreColor(value)}`}
    >
      {fmtScore(value)}
      <span className="text-xs font-normal"> / 5</span>
    </span>
  )
}

// Wraps each weak-moment quote found in `text` in a <mark> with the reason as a tooltip.
function Highlighted({ text, moments = [] }) {
  const lower = text.toLowerCase()
  const spans = []
  for (const m of moments) {
    const at = lower.indexOf(m.quote.toLowerCase())
    if (at >= 0 && !spans.some((s) => at < s.end && at + m.quote.length > s.start)) {
      spans.push({ start: at, end: at + m.quote.length, why: m.why })
    }
  }
  spans.sort((a, b) => a.start - b.start)
  const parts = []
  let pos = 0
  for (const s of spans) {
    if (s.start > pos) parts.push(text.slice(pos, s.start))
    parts.push(
      <mark key={s.start} title={s.why} className="rounded bg-amber-200/70 px-0.5">
        {text.slice(s.start, s.end)}
      </mark>,
    )
    pos = s.end
  }
  parts.push(text.slice(pos))
  return <>{parts}</>
}

function Delivery({ d }) {
  if (!d) return null
  const fillers = Object.entries(d.fillers || {})
  return (
    <div className="text-sm">
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-slate-700">
        <div>
          <dt className="inline text-slate-500">Time </dt>
          <dd className="inline tabular-nums">
            {fmtTime(d.duration_sec)}
            {d.budget_sec ? ` of ${fmtTime(d.budget_sec)}` : ''}
          </dd>
        </div>
        <div>
          <dt className="inline text-slate-500">Words </dt>
          <dd className="inline tabular-nums">{d.words}</dd>
        </div>
        {d.wpm != null && (
          <div>
            <dt className="inline text-slate-500">Pace </dt>
            <dd className="inline tabular-nums">{d.wpm} wpm</dd>
          </div>
        )}
        {d.spoken && (
          <div>
            <dt className="inline text-slate-500">Fillers </dt>
            <dd className="inline">
              {fillers.length ? fillers.map(([k, v]) => `${k} ×${v}`).join(', ') : 'none'}
            </dd>
          </div>
        )}
      </dl>
      {d.tips?.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
          {d.tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Star({ star }) {
  if (!star) return null
  return (
    <div>
      <h4 className="text-sm font-medium">STAR structure</h4>
      <ul className="mt-1 flex flex-wrap gap-2 text-xs">
        {['situation', 'task', 'action', 'result'].map((k) => (
          <li
            key={k}
            className={`rounded-full px-2 py-0.5 capitalize ${star[k] ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500 line-through'}`}
          >
            {k}
          </li>
        ))}
      </ul>
      {star.note && <p className="mt-1 text-sm text-slate-600">{star.note}</p>}
    </div>
  )
}

function Evaluation({ e, said }) {
  return (
    <div className="space-y-5">
      {e.summary && <p className="text-slate-700">{e.summary}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
            What you said
          </h4>
          {said.map((s, i) => (
            <div key={i} className="mb-2 last:mb-0">
              {s.is_follow_up && <p className="text-xs italic text-slate-500">Follow-up: {s.interviewer}</p>}
              <p className="whitespace-pre-wrap">
                <Highlighted text={s.answer} moments={e.weak_moments} />
              </p>
            </div>
          ))}
        </div>
        <div className="rounded-md bg-indigo-50 p-3 ring-1 ring-indigo-100">
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-indigo-700">
            A stronger version
          </h4>
          <p className="whitespace-pre-wrap">{e.stronger_version}</p>
          <p className="mt-2 text-xs text-indigo-700">
            Built only from your résumé and answers. Fill in the [bracketed] parts with your
            real details.
          </p>
        </div>
      </div>

      {e.weak_moments.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Weak moments</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {e.weak_moments.map((w) => (
              <li key={w.quote}>
                <mark className="rounded bg-amber-200/70 px-0.5">“{w.quote}”</mark>{' '}
                <span className="text-slate-600">— {w.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e.changes.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">What changed and why</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {e.changes.map((c, i) => (
              <li key={i}>
                <span className={`mr-2 rounded px-1.5 py-0.5 text-xs capitalize ${CHANGE[c.kind]}`}>
                  {c.kind}
                </span>
                {c.text}
                {c.reason && <span className="text-slate-600"> — {c.reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {e.missing_points.length > 0 && (
          <div>
            <h4 className="text-sm font-medium">What a strong answer covers</h4>
            <ul className="mt-1 space-y-1 text-sm">
              {e.missing_points.map((m) => (
                <li key={m.point} className="flex gap-2">
                  <span aria-label={m.covered ? 'Covered' : 'Missing'} className={m.covered ? 'text-green-700' : 'text-red-600'}>
                    {m.covered ? '✓' : '✗'}
                  </span>
                  <span className={m.covered ? 'text-slate-600' : ''}>{m.point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h4 className="text-sm font-medium">Rubric</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {e.criteria.map((c) => (
              <li key={c.name}>
                <span className="font-medium tabular-nums">{c.score}/5</span> {c.name}
                {c.comment && <span className="text-slate-600"> — {c.comment}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Star star={e.star} />
      {e.tips.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Tips for this question</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {e.tips.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function TryAgain({ sessionId, question, beforeScore, onAttempt }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState(() => (canRecord() ? 'voice' : 'text'))
  const [text, setText] = useState('')
  const [phase, setPhase] = useState('idle') // idle | transcribing | scoring
  const [error, setError] = useState('')
  const [started, setStarted] = useState(0)
  const busy = phase !== 'idle'

  async function send(answer, meta) {
    setPhase('scoring')
    try {
      const data = await api(`/sessions/${sessionId}/questions/${question.question_id}/retry`, {
        method: 'POST',
        body: { text: answer, ...meta },
      })
      setText('')
      onAttempt(question.question_id, data.attempt)
    } catch (err) {
      setError(err.message)
      setText(answer)
      if (meta.input_mode === 'voice') setMode('text')
    } finally {
      setPhase('idle')
    }
  }

  async function onRecorded(blob, durationMs) {
    setError('')
    setPhase('transcribing')
    const form = new FormData()
    form.append('audio', blob, `answer.${EXT[blob.type.split(';')[0]] ?? 'webm'}`)
    let transcript
    try {
      transcript = (await api(`/sessions/${sessionId}/transcribe`, { method: 'POST', body: form })).text
    } catch (err) {
      setError(err.message)
      setPhase('idle')
      return
    }
    await send(transcript, { duration_ms: Math.min(durationMs, MAX_ANSWER_MS), input_mode: 'voice' })
  }

  function sendTyped(e) {
    e.preventDefault()
    if (!text.trim() || busy) return
    setError('')
    send(text, { duration_ms: Math.min(Date.now() - started, MAX_ANSWER_MS), input_mode: 'text' })
  }

  const last = question.attempts.at(-1)
  return (
    <div className="space-y-3 print:hidden">
      {question.attempts.length > 0 && (
        <div className="rounded-md bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
          <p className="font-medium">
            Try again: <Score value={beforeScore} label="Before" /> →{' '}
            <Score value={last.evaluation?.score} label="After" />
            <span className="ml-2 font-normal text-slate-500">
              (attempt {last.attempt_no})
            </span>
          </p>
          <p className="mt-2 whitespace-pre-wrap text-slate-700">{last.answer}</p>
          {last.evaluation && (
            <details className="mt-2">
              <summary className="cursor-pointer text-indigo-700">Feedback on this attempt</summary>
              <div className="mt-3">
                <Evaluation e={last.evaluation} said={[{ answer: last.answer }]} />
              </div>
            </details>
          )}
        </div>
      )}
      {!open ? (
        <button
          type="button"
          onClick={() => {
            setOpen(true)
            setStarted(Date.now())
          }}
          className="rounded-md border border-indigo-600 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
        >
          Try again
        </button>
      ) : (
        <div className="space-y-2 rounded-md border border-slate-200 p-3">
          <p className="text-sm text-slate-600">Answer “{question.text}” again.</p>
          {mode === 'voice' ? (
            <Recorder onRecorded={onRecorded} disabled={busy} />
          ) : (
            <form onSubmit={sendTyped} className="space-y-2">
              <textarea
                aria-label="Your new answer"
                rows={4}
                value={text}
                disabled={busy}
                onChange={(e) => setText(e.target.value)}
                className="block w-full rounded-md border border-slate-300 px-3 py-2"
              />
              <button
                type="submit"
                disabled={busy || !text.trim()}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                Score my new answer
              </button>
            </form>
          )}
          {busy && (
            <p role="status" className="animate-pulse text-sm text-slate-500">
              {phase === 'transcribing' ? 'Listening back to your answer…' : 'Scoring your answer…'}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="flex gap-4 text-sm">
            {canRecord() && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setMode((m) => (m === 'voice' ? 'text' : 'voice'))}
                className="text-slate-600 underline hover:text-slate-900 disabled:opacity-50"
              >
                {mode === 'voice' ? 'Type instead' : 'Speak instead'}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
              className="text-slate-600 underline hover:text-slate-900 disabled:opacity-50"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function QuestionCard({ q, index, sessionId, onAttempt }) {
  const e = q.evaluation
  return (
    <article className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 break-inside-avoid">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Question {index + 1} · {q.section}
            {q.is_bonus ? ' · bonus' : ''}
          </p>
          <h3 className="mt-1 font-medium">{q.text}</h3>
        </div>
        {e ? <Score value={e.score} /> : <span className="text-sm text-slate-500">Scoring…</span>}
      </header>
      <Delivery d={q.delivery} />
      {e ? (
        <Evaluation e={e} said={q.exchange} />
      ) : (
        <div className="space-y-2">
          {q.exchange.map((s, i) => (
            <p key={i} className="whitespace-pre-wrap text-slate-700">
              {s.answer}
            </p>
          ))}
        </div>
      )}
      {e && <TryAgain sessionId={sessionId} question={q} beforeScore={e.score} onAttempt={onAttempt} />}
    </article>
  )
}

function Summary({ report }) {
  const a = report.analytics
  const [label, color] = VERDICT[report.verdict] ?? ['–', 'bg-slate-100 text-slate-600']
  const fillers = Object.entries(a?.fillers ?? {})
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-white p-5">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Overall</p>
          <p className="text-3xl font-semibold tabular-nums">
            {fmtScore(report.overall_score)}
            <span className="text-base font-normal text-slate-500"> / 5</span>
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 font-medium ${color}`}>{label}</span>
        {report.verdict_reason && <p className="basis-full text-slate-700">{report.verdict_reason}</p>}
      </div>

      {report.takeaways.length > 0 && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-5">
          <h2 className="font-medium">Top 3 takeaways</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            {report.takeaways.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
        </div>
      )}

      {a && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-medium">Delivery</h2>
          <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Answer time</dt>
              <dd className="tabular-nums">
                {fmtTime(a.answer_sec)} of {fmtTime(a.budget_sec)} planned
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Average pace</dt>
              <dd className="tabular-nums">{a.avg_wpm != null ? `${a.avg_wpm} wpm` : 'Spoken answers only'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Filler words</dt>
              <dd>{fillers.length ? fillers.map(([k, v]) => `${k} ×${v}`).join(', ') : 'none'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Over time</dt>
              <dd className="tabular-nums">
                {a.over_budget} of {a.questions} answers
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}

export default function Report() {
  const { id } = useParams()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const build = useCallback(async () => {
    setError('')
    setBusy(true)
    try {
      setReport((await api(`/sessions/${id}/report`, { method: 'POST' })).report)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [id])

  useEffect(() => {
    let cancelled = false
    api(`/sessions/${id}/report`)
      .then((data) => !cancelled && setReport(data.report))
      .catch((err) => {
        if (cancelled) return
        if (err.status === 404) build()
        else setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [id, build])

  const generating = report?.status === 'generating'
  useEffect(() => {
    if (!generating) return
    const t = setTimeout(() => {
      api(`/sessions/${id}/report`)
        .then((data) => setReport(data.report))
        .catch((err) => setError(err.message))
    }, POLL_MS)
    return () => clearTimeout(t)
  }, [id, generating, report])

  function onAttempt(questionId, attempt) {
    setReport((r) => ({
      ...r,
      questions: r.questions.map((q) =>
        q.question_id === questionId ? { ...q, attempts: [...q.attempts, attempt] } : q,
      ),
    }))
  }

  if (!report) {
    return error ? (
      <div className="space-y-3">
        <p role="alert" className="text-red-600">
          {error}
        </p>
        <Link to={`/interview/${id}`} className="text-sm text-indigo-700 underline">
          Back to the interview
        </Link>
      </div>
    ) : (
      <p className="animate-pulse text-slate-500">Preparing your report…</p>
    )
  }

  const { scored, total } = report.progress
  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Your report</h1>
          <p className="mt-1 text-slate-600">
            {report.role_title} · {report.duration_min} minutes · {report.difficulty}
          </p>
        </div>
        <div className="flex gap-3 text-sm print:hidden">
          <Link to={`/interview/${id}`} className="text-slate-600 underline hover:text-slate-900">
            Transcript
          </Link>
          <button type="button" onClick={() => window.print()} className="text-slate-600 underline hover:text-slate-900">
            Print / save as PDF
          </button>
        </div>
      </header>

      <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-600">
        Scores are practice feedback from an AI coach, not a hiring assessment.
        {report.licensed_field &&
          ' For licensed or specialized professions, they are not a professional evaluation of your competence.'}
      </p>

      {generating && (
        <p role="status" className="animate-pulse text-slate-600">
          Scoring your answers… {scored} of {total} questions done.
        </p>
      )}
      {report.status === 'failed' && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          Part of the report couldn't be generated ({scored} of {total} questions scored).{' '}
          <button type="button" onClick={build} disabled={busy} className="font-medium underline">
            {busy ? 'Retrying…' : 'Finish the report'}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {total === 0 && !generating && <p className="text-slate-600">You didn't answer any questions, so there's nothing to score.</p>}

      {report.status === 'ready' && total > 0 && <Summary report={report} />}

      <div className="space-y-4">
        {report.questions.map((q, i) => (
          <QuestionCard key={q.question_id} q={q} index={i} sessionId={report.session_id} onAttempt={onAttempt} />
        ))}
      </div>
    </section>
  )
}
