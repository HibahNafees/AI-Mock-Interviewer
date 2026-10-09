import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const NAV = [
  ['/', 'Dashboard'],
  ['/setup', 'New interview'],
  ['/stories', 'Story bank'],
  ['/decoder', 'JD decoder'],
  ['/debrief', 'Debrief'],
]

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span
        aria-hidden="true"
        className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-violet-600 via-fuchsia-500 to-pink-400 text-white shadow-md shadow-fuchsia-500/30"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
        </svg>
      </span>
      <span className="text-lg font-bold tracking-tight text-slate-900">
        Mock<span className="gradient-text">Interviewer</span>
      </span>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen text-slate-800">
      <header className="sticky top-0 z-10 border-b border-white/60 bg-white/70 backdrop-blur-md print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <Link to="/" aria-label="AI Mock Interviewer home">
            <Logo />
          </Link>
          <nav className="flex flex-wrap gap-1 text-sm">
            {NAV.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1.5 font-medium transition ${
                    isActive
                      ? 'bg-violet-100 text-violet-700'
                      : 'text-slate-600 hover:bg-white hover:text-slate-900'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          {user && (
            <div className="ml-auto flex items-center gap-3 text-sm">
              <span className="flex items-center gap-2 text-slate-700">
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-teal-400 to-sky-500 text-xs font-bold text-white"
                >
                  {user.name?.[0]?.toUpperCase()}
                </span>
                {user.name}
              </span>
              <button onClick={logout} className="btn-link">
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
