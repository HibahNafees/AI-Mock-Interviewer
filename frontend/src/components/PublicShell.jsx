import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Logo } from './Layout'
import ThemeToggle from './ThemeToggle'

// Header for pages anyone can open without an account (decoder, shared reports).
export default function PublicShell({ children }) {
  const { user } = useAuth()
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-cream/85 backdrop-blur-md print:hidden">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link to="/">
            <Logo />
          </Link>
          <nav className="ml-auto flex items-center gap-3 text-sm">
            <ThemeToggle />
            {user ? (
              <Link to="/" className="btn-secondary">
                Go to my dashboard
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn-link">
                  Log in
                </Link>
                <Link to="/signup" className="btn-primary px-4 py-2 text-sm">
                  Sign up free
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:py-10">{children}</main>
    </div>
  )
}
