import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada Lovelace', email: 'ada@example.com' }
const SESSIONS = [
  { id: 7, role_title: 'Backend Engineer', status: 'completed', mode: 'standard', duration_min: 10, created_at: '2026-10-12T10:00:00Z' },
  { id: 8, role_title: 'Data Analyst', status: 'planned', mode: 'standard', duration_min: 30, created_at: '2026-10-13T10:00:00Z' },
]

function respond(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      calls.push({ key, opts })
      const hit = routes[key]
      if (!hit) throw new Error(`unexpected ${key}`)
      const [status, body] = hit
      return { ok: status < 400, status, json: async () => body }
    }),
  )
  return calls
}

function renderAt(path) {
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('Dashboard interviews (T-136)', () => {
  it('asks before deleting and keeps the interview on Cancel', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions': [200, { sessions: SESSIONS }],
      'GET /api/stats': [200, { stats: null }],
    })
    renderAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete the interview Backend Engineer' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Backend Engineer'))
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    expect(calls.some((c) => c.key.startsWith('DELETE'))).toBe(false)
  })

  it('deletes an interview once confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions': [200, { sessions: SESSIONS }],
      'GET /api/stats': [200, { stats: null }],
      'DELETE /api/sessions/7': [200, { ok: true }],
    })
    renderAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete the interview Backend Engineer' }))
    await vi.waitFor(() => expect(screen.queryByText('Backend Engineer')).not.toBeInTheDocument())
    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'DELETE /api/sessions/7')).toBe(true)
  })
})
