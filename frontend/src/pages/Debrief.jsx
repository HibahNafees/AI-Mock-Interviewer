import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { IconTile } from '../components/Art'
import DocumentInput from '../components/DocumentInput'
import Recorder from '../components/Recorder'
import { api } from '../lib/api'
import { canRecord, MAX_ANSWER_MS } from '../lib/recording'

const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }
const BLANK = { question: '', answer: '', input_mode: 'text', duration_ms: null }

export function NoRecordingsNotice() {
  return (
    <p role="note" className="rounded-2xl bg-navy-50 p-4 text-sm text-navy-800 ring-1 ring-navy-100">
      <span className="font-bold">Recall only, never recordings.</span> Recording an interviewer without their consent
      is illegal in some places, so this app never accepts audio or video of a real interview. Write (or say) what you
      remember: spoken recall is transcribed and the clip is discarded; only your text is saved.
    </p>
  )
}

function Item({ n, item, onChange, onRemove, canRemove }) {
  const [phase, setPhase] = useState('idle')
  const [error, setError] = useState('')

  async function onRecorded(blob, durationMs) {
    setError('')
    setPhase('transcribing')
    const form = new FormData()
    form.append('audio', blob, `recall.${EXT[blob.type.split(';')[0]] ?? 'webm'}`)
    try {
      const { text } = await api('/debriefs/transcribe', { method: 'POST', body: form })
      onChange({
        ...item,
        answer: item.answer ? `${item.answer} ${text}` : text,
        input_mode: 'voice',
        duration_ms: Math.min(durationMs, MAX_ANSWER_MS),
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setPhase('idle')
    }
  }

  return (
    <li className="card space-y-3 p-5">
      <div className="flex items-center justify-between">
        <p className="eyebrow">Question {n}</p>
        {canRemove && (
          <button type="button" onClick={onRemove} className="btn-link hover:text-red-600">
            Remove
          </button>
        )}
      </div>
      <label className="block text-sm font-medium text-slate-700">
        What they asked
        <textarea
          rows={2}
          value={item.question}
          onChange={(e) => onChange({ ...item, question: e.target.value })}
          placeholder="e.g. Tell me about a time you handled a production incident."
          className="field mt-1 text-sm"
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        What you answered (as best you remember)
        <textarea
          rows={4}
          value={item.answer}
          onChange={(e) => onChange({ ...item, answer: e.target.value, input_mode: 'text' })}
          className="field mt-1 text-sm"
        />
      </label>
      {canRecord() && (
        <div className="space-y-1">
          <p className="text-xs text-slate-500">Or say your answer again from memory:</p>
          <Recorder onRecorded={onRecorded} disabled={phase !== 'idle'} />
          {phase === 'transcribing' && (
            <p role="status" className="animate-pulse text-sm text-slate-500">
              Transcribing…
            </p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </li>
  )
}

export default function Debrief() {
  const navigate = useNavigate()
  const [role, setRole] = useState('')
  const [company, setCompany] = useState('')
  const [round, setRound] = useState('')
  const [jdId, setJdId] = useState(null)
  const [items, setItems] = useState([{ ...BLANK }])
  const [past, setPast] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function removeDebrief(d) {
    if (!window.confirm(`Delete the debrief "${d.role}"? Its report goes with it.`)) return
    try {
      await api(`/debriefs/${d.id}`, { method: 'DELETE' })
      setPast((all) => all.filter((x) => x.id !== d.id))
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    api('/debriefs')
      .then((d) => setPast(d.debriefs ?? []))
      .catch(() => {})
  }, [])

  const ready = role.trim() && items.some((i) => i.question.trim().length >= 3 && i.answer.trim())

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { debrief } = await api('/debriefs', {
        method: 'POST',
        body: {
          role,
          company: company || null,
          round: round || null,
          jd_id: jdId,
          items: items.filter((i) => i.question.trim().length >= 3 && i.answer.trim()),
        },
      })
      navigate(`/report/${debrief.session_id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Post-interview debrief</p>
          <h1 className="mt-1 text-3xl font-extrabold">How did the real one go?</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Recall the questions and your answers. You'll get scores, stronger versions, and the questions the next
            round will likely ask, ready to practice.
          </p>
        </div>
        <IconTile tone="navy" className="hidden h-14 w-14 text-2xl sm:grid">
          📝
        </IconTile>
      </header>

      <NoRecordingsNotice />

      <form onSubmit={submit} className="space-y-4">
        <div className="card grid gap-4 p-5 sm:grid-cols-3">
          <label className="block text-sm font-medium text-slate-700">
            Role
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              required
              className="field mt-1"
              placeholder="Backend Engineer"
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Company <span className="font-normal text-slate-400">(optional)</span>
            <input value={company} onChange={(e) => setCompany(e.target.value)} className="field mt-1" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Round <span className="font-normal text-slate-400">(optional)</span>
            <input
              value={round}
              onChange={(e) => setRound(e.target.value)}
              className="field mt-1"
              placeholder="Phone screen"
            />
          </label>
        </div>
        <DocumentInput
          kind="job_description"
          value={jdId}
          onChange={setJdId}
          optional
          hint="(optional: scores against what the job needs)"
        />

        <ol className="space-y-4">
          {items.map((item, i) => (
            <Item
              key={i}
              n={i + 1}
              item={item}
              canRemove={items.length > 1}
              onChange={(next) => setItems((all) => all.map((x, j) => (j === i ? next : x)))}
              onRemove={() => setItems((all) => all.filter((_, j) => j !== i))}
            />
          ))}
        </ol>
        {items.length < 15 && (
          <button type="button" onClick={() => setItems((all) => [...all, { ...BLANK }])} className="btn-secondary">
            + Add another question
          </button>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <div>
          <button type="submit" disabled={busy || !ready} className="btn-primary">
            {busy ? 'Scoring your debrief…' : 'Score my debrief'}
          </button>
        </div>
      </form>

      {past.length > 0 && (
        <div>
          <h2 className="text-xl font-bold">Past debriefs</h2>
          <ul className="card mt-3 divide-y divide-line-soft overflow-hidden">
            {past.map((d) => (
              <li key={d.id} className="flex items-center hover:bg-brand-50/60">
                <Link
                  to={`/report/${d.session_id}`}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3 py-4 pl-5"
                >
                  <span>
                    <span className="font-semibold text-ink">{d.role}</span>
                    <span className="text-sm text-slate-500">
                      {d.company ? ` · ${d.company}` : ''}
                      {d.round ? ` · ${d.round}` : ''} · {d.items} questions
                    </span>
                  </span>
                  <span className="chip bg-navy-50 text-navy-700">Debrief</span>
                </Link>
                <button
                  type="button"
                  onClick={() => removeDebrief(d)}
                  aria-label={`Delete the debrief ${d.role}`}
                  className="btn-link shrink-0 px-5 text-sm hover:text-red-600"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
