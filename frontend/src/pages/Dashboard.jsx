import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export default function Dashboard() {
  const { user } = useAuth()
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
    </section>
  )
}
