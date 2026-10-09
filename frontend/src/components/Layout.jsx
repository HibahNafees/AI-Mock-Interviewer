import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const NAV = [
  ['/', 'Dashboard'],
  ['/setup', 'New interview'],
  ['/stories', 'Story bank'],
  ['/decoder', 'JD decoder'],
  ['/debrief', 'Debrief'],
]

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold">AI Mock Interviewer</span>
          <nav className="flex flex-wrap gap-4 text-sm">
            {NAV.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  isActive ? 'font-medium text-indigo-600' : 'text-slate-600 hover:text-slate-900'
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          {user && (
            <div className="ml-auto flex items-center gap-3 text-sm">
              <span className="text-slate-600">{user.name}</span>
              <button onClick={logout} className="text-slate-600 underline hover:text-slate-900">
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
