import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IconTile, Mascot } from '../components/Art'
import { useDialogs } from '../components/ConfirmDialog'
import { api } from '../lib/api'

const PARTS = [
  ['situation', 'Situation', 'The context'],
  ['task', 'Task', 'What you had to achieve'],
  ['action', 'Action', 'What you did'],
  ['result', 'Result', 'What changed'],
]

function fmt(score) {
  return score == null ? '–' : score.toFixed(1)
}

function strengthTone(s) {
  if (s == null) return 'bg-slate-100 text-slate-500'
  if (s >= 4) return 'bg-emerald-100 text-emerald-700'
  if (s >= 3) return 'bg-accent-100 text-accent-700'
  return 'bg-brand-100 text-brand-700'
}

function Coverage({ coverage }) {
  const coreGaps = coverage.rows.filter((r) => r.core && r.stories.length === 0).map((r) => r.competency)
  return (
    <div className="card space-y-4 p-6">
      <div>
        <h2 className="text-lg font-bold">Coverage</h2>
        <p className="text-sm text-slate-500">
          Which skills your stories can show{coverage.job ? `, including what ${coverage.job} needs` : ''}
        </p>
      </div>
      <ul className="flex flex-wrap gap-2">
        {coverage.rows.map((r) => (
          <li
            key={r.competency}
            className={`chip ring-1 ${
              r.stories.length
                ? 'bg-emerald-50 text-emerald-800 ring-emerald-200'
                : 'border border-dashed border-slate-300 bg-surface text-slate-500 ring-transparent'
            }`}
          >
            {r.stories.length ? <span aria-hidden="true">✓</span> : <span aria-hidden="true">○</span>}
            {r.competency}
            {r.stories.length > 0 && <span className="font-normal">· {r.stories.length}</span>}
          </li>
        ))}
      </ul>
      {coreGaps.length > 0 && (
        <p className="rounded-xl bg-accent-50 p-3 text-sm text-accent-700 ring-1 ring-accent-200">
          <span className="font-semibold">Gaps:</span> no story yet for {coreGaps.join(', ').toLowerCase()}.
          Think of a real example for each before your next interview.
        </p>
      )}
    </div>
  )
}

function StoryEditor({ story, onSave, onCancel }) {
  const [title, setTitle] = useState(story.title)
  const [star, setStar] = useState(() => ({ ...story.star }))
  const [competencies, setCompetencies] = useState(story.competencies.join(', '))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await onSave({
        title,
        ...Object.fromEntries(PARTS.map(([k]) => [k, star[k] ?? ''])),
        competencies: competencies.split(',').map((c) => c.trim()).filter(Boolean),
      })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <label className="block text-sm font-medium text-slate-700">
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="field mt-1" required />
      </label>
      {PARTS.map(([key, label, hint]) => (
        <label key={key} className="block text-sm font-medium text-slate-700">
          {label} <span className="font-normal text-slate-400">· {hint}</span>
          <textarea
            rows={2}
            value={star[key] ?? ''}
            onChange={(e) => setStar((s) => ({ ...s, [key]: e.target.value }))}
            className="field mt-1 text-sm"
          />
        </label>
      ))}
      <label className="block text-sm font-medium text-slate-700">
        Skills it shows <span className="font-normal text-slate-400">· comma-separated</span>
        <input value={competencies} onChange={(e) => setCompetencies(e.target.value)} className="field mt-1" />
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <button type="submit" disabled={busy} className="btn-primary text-sm">
          {busy ? 'Saving…' : 'Save story'}
        </button>
        <button type="button" onClick={onCancel} className="btn-link">
          Cancel
        </button>
      </div>
    </form>
  )
}

function StoryCard({ story, onChange, onDelete }) {
  const [editing, setEditing] = useState(false)
  const { confirm, notify } = useDialogs()

  async function save(body) {
    const data = await api(`/stories/${story.id}`, { method: 'PUT', body })
    onChange(data.story)
    setEditing(false)
  }

  async function remove() {
    const deleted = await confirm({
      title: 'Delete this story?',
      message: `“${story.title}” will be removed from your story bank. This can’t be undone.`,
      confirmLabel: 'Delete',
      busyLabel: 'Deleting…',
      danger: true,
      onConfirm: () => api(`/stories/${story.id}`, { method: 'DELETE' }),
    })
    if (!deleted) return
    onDelete(story.id)
    notify('Story deleted')
  }

  return (
    <article className="card space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-bold">{story.title}</h3>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {story.competencies.map((c) => (
              <li key={c} className="chip bg-navy-50 text-navy-700">
                {c}
              </li>
            ))}
          </ul>
        </div>
        <span
          aria-label={`Strength ${fmt(story.strength)} out of 5`}
          className={`chip tabular-nums ${strengthTone(story.strength)}`}
        >
          {fmt(story.strength)} / 5
        </span>
      </header>

      {editing ? (
        <StoryEditor story={story} onSave={save} onCancel={() => setEditing(false)} />
      ) : (
        <>
          <dl className="grid gap-3 sm:grid-cols-2">
            {PARTS.map(([key, label]) => (
              <div
                key={key}
                className={`rounded-2xl p-3 ring-1 ${story.star[key] ? 'bg-slate-50 ring-slate-200' : 'bg-accent-50 ring-accent-200'}`}
              >
                <dt className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{label}</dt>
                <dd className="mt-1 text-sm text-slate-800">
                  {story.star[key] ?? (
                    <span className="text-accent-700">Not said yet. Add it so the story lands.</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {story.sources.length > 0 && (
            <p className="text-xs text-slate-500">
              From:{' '}
              {story.sources.map((s, i) => (
                <span key={`${s.session_id}-${i}`}>
                  {i > 0 && ' · '}
                  <Link to={`/report/${s.session_id}`} className="underline hover:text-brand-700">
                    {s.role}, {new Date(`${s.date}T00:00:00`).toLocaleDateString()}
                  </Link>
                </span>
              ))}
              {story.user_edited && ' · edited by you'}
            </p>
          )}
          <div className="flex gap-4 border-t border-slate-100 pt-3">
            <button type="button" onClick={() => setEditing(true)} className="btn-link">
              <span aria-hidden="true">✎ </span>Edit
            </button>
            <button type="button" onClick={remove} className="btn-link hover:text-red-600">
              Delete
            </button>
          </div>
        </>
      )}
    </article>
  )
}

export default function Stories() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/stories')
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <p role="alert" className="text-red-600">{error}</p>
  if (!data) return <p className="text-slate-500">Loading…</p>

  const { stories, coverage } = data
  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Story bank</p>
          <h1 className="mt-1 text-3xl font-extrabold">Your stories</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Real experiences from your answers, in your own words, ready to reuse. Missing parts are
            flagged, never filled in for you. Edit anything that isn't quite right.
          </p>
        </div>
        <IconTile tone="accent" className="hidden h-14 w-14 text-2xl sm:grid">
          📚
        </IconTile>
      </header>

      {stories.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 p-10 text-center">
          <Mascot className="h-24 w-24" />
          <p className="text-lg font-bold text-ink">No stories yet</p>
          <p className="max-w-md text-sm text-slate-600">
            After each interview report, the specific experiences you describe are saved here
            as STAR stories you can practice and reuse.
          </p>
          <Link to="/setup" className="btn-primary mt-2">
            Start a practice interview
          </Link>
        </div>
      ) : (
        <>
          <Coverage coverage={coverage} />
          <div className="space-y-4">
            {stories.map((s) => (
              <StoryCard
                key={s.id}
                story={s}
                onChange={(updated) =>
                  setData((d) => ({ ...d, stories: d.stories.map((x) => (x.id === updated.id ? updated : x)) }))
                }
                onDelete={(id) => setData((d) => ({ ...d, stories: d.stories.filter((x) => x.id !== id) }))}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
