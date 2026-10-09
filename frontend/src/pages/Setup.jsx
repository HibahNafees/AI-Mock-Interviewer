import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DocumentInput from '../components/DocumentInput'
import { api } from '../lib/api'

const DURATIONS = [10, 30, 45, 60]

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
          className={`rounded-md border px-3 py-1.5 text-sm ${
            value === key
              ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
              : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400'
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
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { session } = await api('/sessions', {
        method: 'POST',
        body: { resume_id: resumeId, jd_id: jdId, duration_min: duration, difficulty, persona },
      })
      navigate(`/interview/${session.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <h1 className="text-2xl font-semibold">New interview</h1>

      <div className="grid gap-4 md:grid-cols-2">
        <DocumentInput kind="resume" value={resumeId} onChange={setResumeId} />
        <DocumentInput kind="job_description" value={jdId} onChange={setJdId} />
      </div>

      <section className="space-y-2">
        <h2 className="font-medium">Length</h2>
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
            />
            <span>{duration} minutes</span>
          </label>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Difficulty</h2>
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

      <section className="space-y-2">
        <h2 className="font-medium">Interviewer</h2>
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

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !resumeId || !jdId}
        className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {busy ? 'Building your interview plan…' : 'Build my interview plan'}
      </button>
      {busy && (
        <p className="text-sm text-slate-500">
          Reading the job description and your résumé; this takes a few seconds.
        </p>
      )}
    </form>
  )
}
