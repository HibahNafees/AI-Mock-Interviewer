import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { HeroScene, IconTile, Mascot } from '../components/Art'
import ScoreChart from '../components/ScoreChart'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const STATUS = {
  planned: ['Plan ready', 'bg-navy-100 text-navy-700'],
  active: ['In progress', 'bg-accent-100 text-accent-700'],
  completed: ['Report', 'bg-emerald-100 text-emerald-700'],
  abandoned: ['Cancelled', 'bg-slate-100 text-slate-500'],
}

const TIPS = [
  'Lead with the answer in one sentence, then give the story behind it.',
  'Numbers stick: "cut load time from 4 s to 1 s" beats "made it faster".',
  'A short pause before answering sounds confident, not unsure.',
  'For "Tell me about a time…", use Situation, Task, Action, Result.',
  'End each answer with what you learned or what changed because of you.',
  "It's fine to say \"Let me think about that for a second.\"",
  'Prepare three stories that show different strengths; most questions fit one.',
]

const STEPS = [
  ['📄', 'Add your résumé and the job', 'Paste or upload both; we work out the role and what it needs.', 'brand'],
  ['🎙️', 'Answer out loud', 'A timed interview that adapts to what you say, like the real thing.', 'accent'],
  ['📈', 'Get a scored report', 'Scores, weak moments, and a stronger version of every answer.', 'navy'],
]

function fmt(score) {
  return score == null ? '–' : score.toFixed(1)
}

function scoreTone(s) {
  if (s == null) return 'bg-slate-100 text-slate-500'
  if (s >= 4) return 'bg-emerald-100 text-emerald-700'
  if (s >= 3) return 'bg-accent-100 text-accent-700'
  return 'bg-brand-100 text-brand-700'
}

function Stat({ icon, tone, label, value, sub }) {
  return (
    <div className="card flex items-center gap-4 p-5">
      <IconTile tone={tone}>{icon}</IconTile>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <p className="font-display text-2xl font-extrabold text-ink tabular-nums">{value}</p>
        {sub && <p className="truncate text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  )
}

function LevelCard({ s }) {
  return (
    <div className="card space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Your level</h2>
        <span className="chip bg-accent-100 text-accent-700">
          <span aria-hidden="true">🔥</span>
          {s.streak_days} day{s.streak_days === 1 ? '' : 's'} streak
        </span>
      </div>
      <p className="font-display text-4xl font-extrabold text-ink">
        Level {s.level}
        <span className="text-base font-semibold text-slate-400"> / 10</span>
      </p>
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={`h-2.5 flex-1 rounded-full ${i < s.level ? 'bg-gradient-to-r from-brand-400 to-accent-400' : 'bg-[#f3ebe1]'}`}
          />
        ))}
      </div>
      <p className="text-sm text-slate-600">
        {s.next_level_in == null
          ? 'Top level reached. Keep practicing to stay sharp!'
          : `${s.next_level_in} more interview${s.next_level_in === 1 ? '' : 's'} to reach level ${s.level + 1}.`}
      </p>
      <dl className="grid grid-cols-2 gap-3 border-t border-[#f3ebe1] pt-4 text-sm">
        <div>
          <dt className="text-slate-500">Questions answered</dt>
          <dd className="font-bold text-ink tabular-nums">{s.questions_answered}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Answers retried</dt>
          <dd className="font-bold text-ink tabular-nums">{s.retries}</dd>
        </div>
      </dl>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [tip] = useState(() => TIPS[Math.floor(Math.random() * TIPS.length)])
  const first = user.name.split(' ')[0]

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(data.sessions ?? []))
      .catch(() => {})
    api('/stats')
      .then((data) => setStats(data.stats))
      .catch(() => {})
  }, [])

  const s = stats
  const hasScores = s?.history?.length > 0
  return (
    <section className="space-y-8">
      <div className="relative overflow-hidden rounded-[2rem] border border-[#f6dccf] bg-gradient-to-br from-brand-50 via-white to-accent-50 p-8 sm:p-10">
        <div className="grid items-center gap-6 md:grid-cols-[1fr_18rem]">
          <div>
            <p className="eyebrow">AI mock interview practice</p>
            <h1 className="mt-2 text-4xl font-extrabold sm:text-5xl">
              Welcome, {first} <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-3 max-w-xl text-lg text-slate-600">
              Practice for any job: upload your résumé and a job description, answer out loud,
              and get a scored report with stronger versions of your answers.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/setup" className="btn-primary px-6 py-3 text-base">
                Start a mock interview <span aria-hidden="true">🚀</span>
              </Link>
              {s && s.interviews > 0 && (
                <span className="chip bg-white text-slate-700 ring-1 ring-[#f1e6da]">
                  Level {s.level} · {s.interviews} interview{s.interviews === 1 ? '' : 's'} done
                </span>
              )}
            </div>
          </div>
          <HeroScene className="hidden h-60 md:block" />
        </div>
      </div>

      {s && s.interviews > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon="🎯" tone="brand" label="Mock interviews" value={s.interviews} sub={`${s.started} started`} />
            <Stat icon="⭐" tone="accent" label="Average score" value={`${fmt(s.average_score)} / 5`} sub={s.latest_score != null ? `Latest ${fmt(s.latest_score)}` : null} />
            <Stat icon="🏆" tone="green" label="Best score" value={`${fmt(s.best_score)} / 5`} />
            <Stat icon="⏱️" tone="navy" label="Time practicing" value={`${s.practice_minutes} min`} sub={`${s.questions_answered} questions answered`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
            <div className="card p-6">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-lg font-bold">Your score over time</h2>
                  <p className="text-sm text-slate-500">Overall score of each interview, out of 5</p>
                </div>
                {s.improvement != null && (
                  <span className={`chip ${s.improvement >= 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-brand-100 text-brand-700'}`}>
                    {s.improvement >= 0 ? '▲ +' : '▼ '}
                    {s.improvement.toFixed(1)} since your first
                  </span>
                )}
              </div>
              {hasScores ? (
                <div className="mt-4">
                  <ScoreChart history={s.history} />
                </div>
              ) : (
                <p className="mt-6 text-sm text-slate-500">Open a report to see your first score here.</p>
              )}
            </div>
            <LevelCard s={s} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card p-6">
              <h2 className="text-lg font-bold">Roles you've practiced</h2>
              <ul className="mt-4 space-y-3">
                {s.roles.map((r) => (
                  <li key={r.role} className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-3">
                      <IconTile tone="navy" className="h-9 w-9 text-sm font-bold text-navy-800">
                        {r.role[0]}
                      </IconTile>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink">{r.role}</span>
                        <span className="text-xs text-slate-500">
                          {r.interviews} interview{r.interviews === 1 ? '' : 's'}
                        </span>
                      </span>
                    </span>
                    <span className={`chip tabular-nums ${scoreTone(r.average_score)}`}>
                      {fmt(r.average_score)} / 5
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-6">
              <h2 className="text-lg font-bold">Your skills</h2>
              <p className="text-sm text-slate-500">Average across all your scored answers</p>
              {s.skills.length ? (
                <ul className="mt-4 space-y-3">
                  {s.skills.map((k) => (
                    <li key={k.name}>
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-slate-700">{k.name}</span>
                        <span className="font-bold text-ink tabular-nums">{fmt(k.score)}</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#f3ebe1]" aria-hidden="true">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-brand-400 to-accent-400"
                          style={{ width: `${(k.score / 5) * 100}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-slate-500">Your skills appear after your first report.</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map(([icon, title, text, tone], i) => (
            <li key={title} className="card p-6">
              <IconTile tone={tone}>{icon}</IconTile>
              <p className="mt-4 text-xs font-bold text-slate-400">STEP {i + 1}</p>
              <h2 className="mt-1 text-lg font-bold">{title}</h2>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      )}

      <div className="flex items-center gap-4 rounded-3xl bg-navy-800 p-6 text-white">
        <Mascot className="h-20 w-20 shrink-0" />
        <div>
          <p className="text-xs font-bold tracking-wider text-accent-300 uppercase">Tip of the day</p>
          <p className="mt-1 text-lg font-semibold">{tip}</p>
        </div>
      </div>

      {sessions.length > 0 && (
        <div>
          <h2 className="text-xl font-bold">Your interviews</h2>
          <ul className="card mt-3 divide-y divide-[#f3ebe1] overflow-hidden">
            {sessions.map((x) => {
              const [label, color] = STATUS[x.status] ?? [x.status, 'bg-slate-100 text-slate-600']
              return (
                <li key={x.id}>
                  <Link
                    to={x.status === 'completed' ? `/report/${x.id}` : `/interview/${x.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-4 transition hover:bg-brand-50/60"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <IconTile tone="brand" className="h-10 w-10 font-bold text-brand-700">
                        {(x.role_title || 'I')[0]}
                      </IconTile>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink">{x.role_title || 'Interview'}</span>
                        <span className="text-sm text-slate-500">
                          {x.duration_min} min · {new Date(x.created_at).toLocaleDateString()}
                        </span>
                      </span>
                    </span>
                    <span className={`chip ${color}`}>{label}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}
