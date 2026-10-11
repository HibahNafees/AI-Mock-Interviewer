import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const DAY = { users: 2, minutes: 12.5, sessions: 3, fire_calls: 40, spend_usd: 0.021, decoder_runs: 1 }
const USAGE = {
  budget_usd: 1,
  month_spend_usd: 0.377,
  budget_left_usd: 0.623,
  paused: false,
  users_total: 9,
  days: [{ date: '2026-10-11', ...DAY }, { date: '2026-10-10', ...DAY, users: 0, minutes: 0, sessions: 0, fire_calls: 0, spend_usd: 0, decoder_runs: 0 }],
  top_users: [{ email: 'ada@example.com', spend_usd: 0.2, minutes: 40, sessions: 4 }],
}

function renderAs(user, usage) {
  localStorage.setItem('mi_token', 'tok')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      if (url === '/api/auth/me') return { ok: true, status: 200, json: async () => ({ user }) }
      if (url === '/api/admin/usage') return usage
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('admin', () => {
  it('shows the budget, active days and top users to admins', async () => {
    renderAs({ id: 1, name: 'Hibah', is_admin: true }, { ok: true, status: 200, json: async () => ({ usage: USAGE }) })
    expect(await screen.findByText('Usage and Fire spend')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Admin' })).toBeInTheDocument()
    expect(screen.getByText('38% used · $0.62 left')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('2026-10-11')).toBeInTheDocument()
    expect(screen.queryByText('2026-10-10')).not.toBeInTheDocument() // days with no usage are hidden
    expect(screen.getByText('ada@example.com')).toBeInTheDocument()
  })

  it('hides the link and shows the error for everyone else', async () => {
    renderAs({ id: 2, name: 'Ada', is_admin: false }, { ok: false, status: 404, json: async () => ({ error: 'Not found' }) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Not found')
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })
})
