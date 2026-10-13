import { render, screen, within } from '@testing-library/react'
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
      const [status, body] = typeof hit === 'function' ? hit(opts) : hit
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
  localStorage.clear()
})

const ROUTES = {
  'GET /api/auth/me': [200, { user: ADA }],
  'GET /api/sessions': [200, { sessions: SESSIONS }],
  'GET /api/stats': [200, { stats: null }],
}

// Five interviews, newest first (the order the API returns them in).
const MANY = ['Backend Engineer', 'Data Analyst', 'Product Manager', 'Nurse', 'Teacher'].map((role_title, i) => ({
  id: 20 + i,
  role_title,
  status: 'completed',
  mode: 'standard',
  duration_min: 10,
  created_at: `2026-10-${13 - i}T10:00:00Z`,
}))

describe('Dashboard interviews (T-136, T-137)', () => {
  it('asks in the app dialog before deleting and keeps the interview on Cancel', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    const calls = respond(ROUTES)
    renderAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete the interview Backend Engineer' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete this interview?' })
    expect(dialog).toHaveTextContent(
      '“Backend Engineer” and its answers and report will be permanently deleted. This can’t be undone.',
    )
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
    expect(calls.some((c) => c.key.startsWith('DELETE'))).toBe(false)
    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('deletes once confirmed, then says so', async () => {
    let finish
    const calls = respond({
      ...ROUTES,
      'DELETE /api/sessions/7': () => [200, { ok: true }],
    })
    // Hold the DELETE open to see the loading state.
    const fetch = globalThis.fetch
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'DELETE' ? new Promise((resolve) => (finish = () => resolve(fetch(url, opts)))) : fetch(url, opts),
    )
    renderAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete the interview Backend Engineer' }))
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    expect(within(dialog).getByRole('button', { name: 'Deleting…' })).toBeDisabled()
    finish()
    await vi.waitFor(() => expect(screen.queryByText('Backend Engineer')).not.toBeInTheDocument())
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Interview deleted')
    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'DELETE /api/sessions/7')).toBe(true)
  })

  it('collapses to the 3 most recent with Show all, and remembers the choice', async () => {
    respond({ ...ROUTES, 'GET /api/sessions': [200, { sessions: MANY }] })
    renderAt('/')
    const list = await screen.findByRole('list', { name: 'Your interviews' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(5) // full list by default
    const toggle = screen.getByRole('button', { name: 'Show less' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    await userEvent.click(toggle)
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)
    expect(within(list).getByText('Product Manager')).toBeInTheDocument()
    expect(within(list).queryByText('Nurse')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show more' })).toHaveAttribute('aria-expanded', 'false')
    expect(localStorage.getItem('mi_interviews_expanded')).toBe('0')

    await userEvent.click(screen.getByRole('button', { name: 'Show all (5)' }))
    expect(within(list).getAllByRole('listitem')).toHaveLength(5)
    expect(screen.queryByRole('button', { name: /Show all/ })).not.toBeInTheDocument()
    expect(localStorage.getItem('mi_interviews_expanded')).toBeNull()
  })

  it('opens collapsed next time when it was left collapsed', async () => {
    localStorage.setItem('mi_interviews_expanded', '0')
    respond({ ...ROUTES, 'GET /api/sessions': [200, { sessions: MANY }] })
    renderAt('/')
    const list = await screen.findByRole('list', { name: 'Your interviews' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Show all (5)' })).toBeInTheDocument()
  })

  it('has no toggle when there are 3 interviews or fewer', async () => {
    respond(ROUTES)
    renderAt('/')
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show (less|more|all)/ })).not.toBeInTheDocument()
  })
})
