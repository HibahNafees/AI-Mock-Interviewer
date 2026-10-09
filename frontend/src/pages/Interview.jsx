import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PlanEditor from '../components/PlanEditor'
import Recorder from '../components/Recorder'
import Timer from '../components/Timer'
import { api } from '../lib/api'
import { canRecord, MAX_ANSWER_MS } from '../lib/recording'

function Transcript({ items }) {
  return (
    <ol className="space-y-4">
      {items.map((t) => (
        <li key={t.question_id} className="space-y-2">
          <div className="max-w-[85%] rounded-lg bg-white p-3 shadow-sm ring-1 ring-slate-200">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
              Interviewer{t.is_follow_up ? ' · follow-up' : t.is_bonus ? ' · bonus' : ''}
            </p>
            <p>{t.interviewer}</p>
          </div>
          {t.answer && (
            <div className="ml-auto max-w-[85%] rounded-lg bg-indigo-50 p-3 ring-1 ring-indigo-100">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-indigo-700">
                You{t.input_mode === 'voice' ? ' · transcribed' : ''}
              </p>
              <p className="whitespace-pre-wrap">{t.answer}</p>
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}

function PlanStep({ session, setSession }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function savePlan(plan) {
    const data = await api(`/sessions/${session.id}/plan`, { method: 'PUT', body: plan })
    setSession(data.session)
  }

  async function start() {
    setError('')
    setBusy(true)
    try {
      setSession((await api(`/sessions/${session.id}/start`, { method: 'POST' })).session)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const analysis = session.analysis || {}
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Your interview plan</h1>
        <p className="mt-1 text-slate-600">
          {session.role_title} · {session.duration_min} minutes · {session.difficulty} ·{' '}
          {session.persona} interviewer
        </p>
        {analysis.competencies?.length > 0 && (
          <p className="mt-2 text-sm text-slate-600">
            Focus: {analysis.competencies.map((c) => c.name).join(', ')}
          </p>
        )}
        {analysis.licensed_field && (
          <p className="mt-2 rounded-md bg-amber-50 p-2 text-sm text-amber-800">
            Feedback for licensed or specialized professions is for practice only, not a
            professional assessment.
          </p>
        )}
      </header>
      <p className="text-sm text-slate-600">
        Edit any question or the minutes per section, then start when you're ready.
      </p>
      <PlanEditor
        key={session.id}
        plan={session.plan}
        duration={session.duration_min}
        onSave={savePlan}
      />
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {busy ? 'Starting…' : 'Start interview'}
      </button>
    </div>
  )
}

const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }

function LiveStep({ session, setSession }) {
  const [mode, setMode] = useState(() => (canRecord() ? 'voice' : 'text'))
  const [text, setText] = useState('')
  const [phase, setPhase] = useState('idle') // idle | transcribing | thinking
  const [error, setError] = useState('')
  const askedAt = useRef(0)
  const spoken = useRef(null) // {duration_ms} when the text box holds a transcript
  const bottom = useRef(null)
  const active = session.status === 'active'
  const busy = phase !== 'idle'
  const turns = session.transcript.length

  useEffect(() => {
    askedAt.current = Date.now()
    bottom.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [turns])

  async function sendTurn(answer, meta) {
    setPhase('thinking')
    try {
      const data = await api(`/sessions/${session.id}/turns`, { method: 'POST', body: { text: answer, ...meta } })
      setText('')
      spoken.current = null
      setSession(data.session)
    } catch (err) {
      // Keep the answer (typed or transcribed) so it can be resent without re-recording.
      setError(err.message)
      setText(answer)
      if (meta.input_mode === 'voice') {
        spoken.current = { duration_ms: meta.duration_ms }
        setMode('text')
      }
    } finally {
      setPhase('idle')
    }
  }

  async function onRecorded(blob, durationMs) {
    setError('')
    setPhase('transcribing')
    const form = new FormData()
    const type = blob.type.split(';')[0]
    form.append('audio', blob, `answer.${EXT[type] ?? 'webm'}`)
    let transcript
    try {
      transcript = (await api(`/sessions/${session.id}/transcribe`, { method: 'POST', body: form })).text
    } catch (err) {
      setError(err.message)
      setPhase('idle')
      return
    }
    await sendTurn(transcript, {
      duration_ms: Math.min(durationMs, MAX_ANSWER_MS),
      input_mode: 'voice',
    })
  }

  function sendTyped(e) {
    e.preventDefault()
    if (!text.trim() || busy) return
    setError('')
    const meta = spoken.current
      ? { ...spoken.current, input_mode: 'voice' }
      : { duration_ms: Math.min(Date.now() - askedAt.current, MAX_ANSWER_MS), input_mode: 'text' }
    sendTurn(text, meta)
  }

  async function endEarly() {
    if (!window.confirm('End the interview now?')) return
    setSession((await api(`/sessions/${session.id}/end`, { method: 'POST' })).session)
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{session.role_title || 'Interview'}</h1>
          {active && <Timer timer={session.timer} running={!busy} />}
        </div>
        {active && (
          <button
            type="button"
            onClick={endEarly}
            className="text-sm text-slate-600 underline hover:text-slate-900"
          >
            End interview
          </button>
        )}
      </header>

      <Transcript items={session.transcript} />
      {busy && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          {phase === 'transcribing' ? 'Listening back to your answer…' : 'Interviewer is thinking…'}
        </p>
      )}
      <div ref={bottom} />

      {active ? (
        <div className="space-y-3">
          {mode === 'voice' ? (
            <Recorder onRecorded={onRecorded} disabled={busy} />
          ) : (
            <form onSubmit={sendTyped} className="space-y-2">
              <textarea
                aria-label="Your answer"
                rows={5}
                value={text}
                disabled={busy}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendTyped(e)
                }}
                placeholder="Type your answer… (Ctrl+Enter to send)"
                className="block w-full rounded-md border border-slate-300 px-3 py-2"
              />
              <button
                type="submit"
                disabled={busy || !text.trim()}
                className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                Send answer
              </button>
            </form>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          {canRecord() && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setError('')
                spoken.current = null
                setMode((m) => (m === 'voice' ? 'text' : 'voice'))
              }}
              className="text-sm text-slate-600 underline hover:text-slate-900 disabled:opacity-50"
            >
              {mode === 'voice' ? 'Type instead' : 'Speak instead'}
            </button>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="font-medium">Interview finished.</p>
          <p className="mt-1 text-sm text-slate-600">
            Your report scores each answer and shows a stronger version of it.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <Link
              to={`/report/${session.id}`}
              className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
            >
              See your report
            </Link>
            <Link to="/setup" className="text-sm text-indigo-700 underline">
              Start another interview
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Interview() {
  const { id } = useParams()
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api(`/sessions/${id}`)
      .then((data) => setSession(data.session))
      .catch((err) => setError(err.message))
  }, [id])

  useEffect(load, [load])

  if (error) return <p role="alert" className="text-red-600">{error}</p>
  if (!session) return <p className="text-slate-500">Loading…</p>
  if (session.status === 'planned') return <PlanStep session={session} setSession={setSession} />
  return <LiveStep session={session} setSession={setSession} />
}
