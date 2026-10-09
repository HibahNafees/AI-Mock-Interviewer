import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const STATUS = {
  planned: ['Plan ready', 'bg-sky-100 text-sky-700'],
  active: ['In progress', 'bg-amber-100 text-amber-800'],
  completed: ['Report', 'bg-emerald-100 text-emerald-700'],
  abandoned: ['Cancelled', 'bg-slate-100 text-slate-500'],
}

const STEPS = [
  ['1', 'Add your résumé and the job', 'Paste or upload both; we find the role and what it needs.', 'from-violet-500 to-fuchsia-500'],
  ['2', 'Answer out loud', 'A timed interview that adapts to what you say, like the real thing.', 'from-fuchsia-500 to-pink-500'],
  ['3', 'Get a scored report', 'Scores, weak moments, and a stronger version of every answer.', 'from-teal-400 to-sky-500'],
]

export default function Dashboard() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(data.sessions ?? []))
      .catch(() => {})
  }, [])

  return (
    <section className="space-y-10">
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-violet-700 via-fuchsia-600 to-pink-500 p-8 text-white shadow-xl shadow-fuchsia-500/20 sm:p-10">
        <div aria-hidden="true" className="absolute -top-16 -right-16 h-56 w-56 rounded-full bg-white/10 blur-2xl" />
        <div aria-hidden="true" className="absolute -bottom-20 left-1/3 h-56 w-56 rounded-full bg-teal-300/20 blur-3xl" />
        <p className="relative text-sm font-semibold tracking-wider text-white/80 uppercase">
          Practice makes confident
        </p>
        <h1 className="relative mt-2 text-3xl font-extrabold sm:text-4xl">Welcome, {user.name}</h1>
        <p className="relative mt-3 max-w-2xl text-white/90">
          Practice for any job: upload your résumé and a job description, answer out loud, and get
          a scored report with stronger versions of your answers.
        </p>
        <Link
          to="/setup"
          className="relative mt-6 inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 font-semibold text-violet-700 shadow-lg transition hover:bg-violet-50"
        >
          Start a new interview <span aria-hidden="true">→</span>
        </Link>
      </div>

      {sessions.length === 0 && (
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map(([n, title, text, gradient]) => (
            <li key={n} className="card p-5">
              <span
                className={`grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br ${gradient} font-bold text-white`}
              >
                {n}
              </span>
              <h2 className="mt-3 font-semibold text-slate-900">{title}</h2>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      )}

      {sessions.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-slate-900">Your interviews</h2>
          <ul className="card mt-3 divide-y divide-slate-100 overflow-hidden">
            {sessions.map((s) => {
              const [label, color] = STATUS[s.status] ?? [s.status, 'bg-slate-100 text-slate-600']
              return (
                <li key={s.id}>
                  <Link
                    to={s.status === 'completed' ? `/report/${s.id}` : `/interview/${s.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-4 transition hover:bg-violet-50/60"
                  >
                    <span className="flex items-center gap-3">
                      <span
                        aria-hidden="true"
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-100 font-bold text-violet-700"
                      >
                        {(s.role_title || 'I')[0]}
                      </span>
                      <span>
                        <span className="font-semibold text-slate-900">{s.role_title || 'Interview'}</span>{' '}
                        <span className="text-sm text-slate-500">· {s.duration_min} min</span>
                      </span>
                    </span>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${color}`}>{label}</span>
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
