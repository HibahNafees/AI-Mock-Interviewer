import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Mascot } from './Art'

const NAV = [
  ['/', 'Dashboard'],
  ['/setup', 'New interview'],
  ['/stories', 'Story bank'],
  ['/decoder', 'JD decoder'],
  ['/debrief', 'Debrief'],
]

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <Mascot className="h-10 w-10" />
      <span className="font-display text-xl font-extrabold tracking-tight text-ink">
        Mock<span className="text-brand-500">Interviewer</span>
      </span>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen text-slate-800">
      <header className="sticky top-0 z-10 border-b border-[#f1e6da] bg-cream/85 backdrop-blur-md print:hidden">
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
                      ? 'bg-brand-100 text-brand-700'
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
                  className="grid h-8 w-8 place-items-center rounded-full bg-navy-800 text-xs font-bold text-white"
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
