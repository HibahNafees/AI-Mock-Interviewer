import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { IconTile, Mascot } from '../components/Art'
import PublicShell from '../components/PublicShell'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

function Quote({ children }) {
  return <q className="rounded bg-accent-100 px-1 text-sm text-accent-700 italic">{children}</q>
}

function Flags({ title, icon, tone, rows, empty }) {
  return (
    <div className="card p-6">
      <h3 className="flex items-center gap-2 text-lg font-bold">
        <IconTile tone={tone} className="h-8 w-8 text-base">
          {icon}
        </IconTile>
        {title}
      </h3>
      {rows.length ? (
        <ul className="mt-3 space-y-3">
          {rows.map((r) => (
            <li key={r.point} className="text-sm">
              <p className="font-medium text-ink">{r.point}</p>
              <p className="mt-0.5 text-slate-500">
                From the posting: <Quote>{r.evidence}</Quote>
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-slate-500">{empty}</p>
      )}
    </div>
  )
}

function Guess({ label, g }) {
  if (!g) return null
  return (
    <div className="rounded-2xl bg-[#faf5ef] p-4">
      <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{label}</p>
      <p className="mt-1 font-bold text-ink">{g.guess}</p>
      {g.why && <p className="text-sm text-slate-600">{g.why}</p>}
      {g.evidence && (
        <p className="mt-1 text-sm text-slate-500">
          <Quote>{g.evidence}</Quote>
        </p>
      )}
    </div>
  )
}

export function DecodeResult({ d, signedIn }) {
  const [copied, setCopied] = useState(false)
  const link = `${window.location.origin}/decode/${d.share_token}`

  async function copy() {
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
    } catch {
      window.prompt('Copy this link', link)
    }
  }

  return (
    <div className="space-y-5">
      <p role="note" className="rounded-2xl bg-navy-50 p-4 text-sm text-navy-800 ring-1 ring-navy-100">
        <span className="font-bold">Interpretation, not fact.</span> This is an AI reading of the
        posting's wording. Every flag quotes the posting so you can judge for yourself, and
        anything about team, pace or culture is a guess to confirm with the recruiter.
      </p>

      <div className="card space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Decoded</p>
            <h2 className="mt-1 text-2xl font-extrabold">{d.role_title || 'This job'}</h2>
          </div>
          <button type="button" onClick={copy} className="btn-secondary">
            {copied ? 'Link copied' : 'Copy share link'}
          </button>
        </div>
        <p className="text-slate-700">{d.summary}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Guess label="Likely team size" g={d.team_size} />
          <Guess label="Likely pace" g={d.pace} />
        </div>
        {d.signals?.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-slate-700">What the posting keeps repeating</p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {d.signals.map((s) => (
                <li key={s.word} className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-100">
                  “{s.word}” × {s.count}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <Flags
        title="What they really need"
        icon="🎯"
        tone="brand"
        rows={d.priorities}
        empty="Nothing stood out beyond the listed duties."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Flags title="Green flags" icon="✅" tone="green" rows={d.green_flags} empty="None found in the wording." />
        <Flags title="Things to ask about" icon="🚩" tone="accent" rows={d.red_flags} empty="No red flags found in the wording." />
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold">Questions they'll likely ask</h3>
        <ol className="mt-3 space-y-3">
          {d.likely_questions.map((q, i) => (
            <li key={q.question} className="flex gap-3 text-sm">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-navy-800 text-xs font-bold text-white">
                {i + 1}
              </span>
              <span>
                <span className="font-medium text-ink">{q.question}</span>
                {q.why && <span className="block text-slate-500">{q.why}</span>}
              </span>
            </li>
          ))}
        </ol>
        {d.competencies?.length > 0 && (
          <>
            <p className="mt-5 text-sm font-semibold text-slate-700">Skills to prepare</p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {d.competencies.map((c) => (
                <li key={c.name} className="chip bg-navy-50 text-navy-700" title={c.why}>
                  {c.name}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="flex flex-col items-start gap-3 rounded-3xl bg-navy-800 p-6 text-white sm:flex-row sm:items-center">
        <Mascot className="h-16 w-16 shrink-0" />
        <div className="flex-1">
          <p className="text-lg font-semibold">Practice these questions out loud before the real thing.</p>
          <p className="text-sm text-white/75">A timed mock interview for this exact job, with scores and stronger answers.</p>
        </div>
        <Link to={signedIn ? '/setup' : '/signup'} className="btn-primary">
          {signedIn ? 'Practice for this job' : 'Sign up free to practice'}
        </Link>
      </div>
    </div>
  )
}

// A signed-in user's decodes, to come back to or delete (T-64).
function SavedDecodes({ items, onDelete, base }) {
  if (!items.length) return null
  return (
    <section className="card p-6">
      <h2 className="text-lg font-bold">Your saved decodes</h2>
      <ul className="mt-3 divide-y divide-[#f3ebe1]">
        {items.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <Link to={`${base}/${s.share_token}`} className="font-semibold text-ink hover:text-brand-700">
                {s.title}
              </Link>
              <p className="truncate text-sm text-slate-500">
                {new Date(s.saved_at).toLocaleDateString()} · {s.summary}
              </p>
            </div>
            <Link to={`${base}/${s.share_token}`} className="btn-secondary px-3 py-1 text-sm">
              Open
            </Link>
            <button
              type="button"
              onClick={() => onDelete(s)}
              aria-label={`Delete ${s.title}`}
              className="btn-link text-sm hover:text-red-600"
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function Decoder({ standalone = false }) {
  const { user } = useAuth()
  const { token } = useParams()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState([])
  const base = standalone ? '/decode' : '/decoder'

  const loadSaved = useCallback(() => {
    if (!user) return
    api('/decoder/saved')
      .then((data) => setSaved(data.saved))
      .catch(() => {})
  }, [user])
  useEffect(loadSaved, [loadSaved])

  async function remove(s) {
    if (!window.confirm(`Delete the saved decode for "${s.title}"? Its share link stops working too.`)) return
    setError('')
    try {
      await api(`/decoder/saved/${s.id}`, { method: 'DELETE' })
      setSaved((list) => list.filter((x) => x.id !== s.id))
      if (token === s.share_token) navigate(base, { replace: true })
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    if (!token) {
      setResult(null)
      return
    }
    api(`/decoder/${token}`)
      .then((data) => setResult(data.decode))
      .catch((err) => setError(err.message))
  }, [token])

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const data = await api('/decoder', { method: 'POST', body: { text } })
      setResult(data.decode)
      loadSaved()
      if (standalone) navigate(`/decode/${data.decode.share_token}`, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const page = (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Job description decoder</p>
          <h1 className="mt-1 text-3xl font-extrabold sm:text-4xl">Read between the lines</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Paste a job posting to see what it likely means: team size, pace, real priorities,
            red and green flags, and the questions you'll probably be asked.
          </p>
        </div>
        <IconTile tone="navy" className="hidden h-14 w-14 text-2xl sm:grid">
          🔍
        </IconTile>
      </header>

      {!token && (
        <form onSubmit={submit} className="card space-y-3 p-6">
          <label htmlFor="jd-text" className="font-semibold text-ink">
            Job description
          </label>
          <textarea
            id="jd-text"
            rows={9}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the full job posting here…"
            className="field text-sm"
          />
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={busy || text.trim().length < 200} className="btn-primary">
              {busy ? 'Decoding…' : 'Decode this job'}
            </button>
            <span className="text-xs text-slate-500">
              {user
                ? "Up to 5 a day. The results are saved to your list below; the posting itself isn't."
                : "Free, no account needed (3 a day). The posting itself isn't saved."}
            </span>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          Reading between the lines… this takes about 10 seconds.
        </p>
      )}
      {result && <DecodeResult d={result} signedIn={Boolean(user)} />}
      {token && (
        <Link to={base} className="btn-link">
          Decode another job
        </Link>
      )}
      {user && <SavedDecodes items={saved} onDelete={remove} base={base} />}
    </section>
  )

  if (!standalone) return page
  return <PublicShell>{page}</PublicShell>
}
