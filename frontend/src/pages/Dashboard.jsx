import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const STATUS = { planned: 'Plan ready', active: 'In progress', completed: 'Finished', abandoned: 'Cancelled' }

export default function Dashboard() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(data.sessions ?? []))
      .catch(() => {})
  }, [])

  return (
    <section>
      <h1 className="text-2xl font-semibold">Welcome, {user.name}</h1>
      <p className="mt-2 text-slate-600">
        Practice for any job: upload your résumé and a job description, answer out loud, and get
        a scored report with stronger versions of your answers.
      </p>
      <Link
        to="/setup"
        className="mt-6 inline-block rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
      >
        Start a new interview
      </Link>

      {sessions.length > 0 && (
        <div className="mt-10">
          <h2 className="text-lg font-medium">Your interviews</h2>
          <ul className="mt-3 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
            {sessions.map((s) => (
              <li key={s.id}>
                <Link
                  to={`/interview/${s.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                >
                  <span>
                    {s.role_title || 'Interview'}{' '}
                    <span className="text-sm text-slate-500">· {s.duration_min} min</span>
                  </span>
                  <span className="text-sm text-slate-500">{STATUS[s.status] ?? s.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
