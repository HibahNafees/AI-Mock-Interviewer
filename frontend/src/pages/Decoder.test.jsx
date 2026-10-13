import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const DECODE = {
  share_token: 'abc123',
  role_title: 'Backend Engineer',
  summary: 'A backend role that likely centres on talking to stakeholders.',
  team_size: { guess: 'small team', why: 'one product', evidence: null },
  pace: { guess: 'fast-moving', why: 'ships weekly', evidence: 'ship features every week' },
  priorities: [{ point: 'Keeping stakeholders aligned', evidence: 'work closely with stakeholders' }],
  green_flags: [],
  red_flags: [{ point: 'Always on call', evidence: 'on call every other week' }],
  likely_questions: [{ question: 'How do you handle conflicting asks?', why: 'stakeholders × 4' }],
  competencies: [{ name: 'Communication', why: 'stakeholders' }],
  signals: [{ word: 'stakeholders', count: 4 }],
}
const POSTING = 'We want a backend engineer who will work closely with stakeholders. '.repeat(5)

// Paste, as people do: typing 340 characters key by key ran past the 5 s test
// timeout on a busy machine (T-104).
async function paste(field, text) {
  await userEvent.click(field)
  await userEvent.paste(text)
}

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
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('job description decoder', () => {
  it('decodes a posting without signing in', async () => {
    const calls = respond({
      'POST /api/decoder': [200, { decode: DECODE }],
      'GET /api/decoder/abc123': [200, { decode: DECODE }],
    })
    renderAt('/decode')
    await paste(await screen.findByLabelText('Job description'), POSTING)
    await userEvent.click(screen.getByRole('button', { name: 'Decode this job' }))
    expect(await screen.findByText('Interpretation, not fact.')).toBeInTheDocument()
    expect(screen.getByText('Keeping stakeholders aligned')).toBeInTheDocument()
    expect(screen.getByText('ship features every week')).toBeInTheDocument()
    expect(screen.getByText('“stakeholders” × 4')).toBeInTheDocument()
    expect(screen.getByText('How do you handle conflicting asks?')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign up free to practice' })).toHaveAttribute('href', '/signup')
    expect(calls.some((c) => c.key === 'GET /api/auth/me')).toBe(false)
    expect(calls.find((c) => c.key === 'POST /api/decoder').opts.headers.Authorization).toBeUndefined()
  })

  it('opens a shared decode link', async () => {
    respond({ 'GET /api/decoder/abc123': [200, { decode: DECODE }] })
    renderAt('/decode/abc123')
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.queryByLabelText('Job description')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Decode another job' })).toHaveAttribute('href', '/decode')
  })

  it('works inside the app when signed in', async () => {
    localStorage.setItem('mi_token', 'tok')
    respond({
      'GET /api/auth/me': [200, { user: { id: 1, name: 'Ada', email: 'ada@example.com' } }],
      'POST /api/decoder': [200, { decode: DECODE }],
    })
    renderAt('/decoder')
    await paste(await screen.findByLabelText('Job description'), POSTING)
    await userEvent.click(screen.getByRole('button', { name: 'Decode this job' }))
    expect(await screen.findByRole('link', { name: 'Practice for this job' })).toHaveAttribute('href', '/setup')
  })

  it('lists saved decodes to reopen or delete', async () => {
    localStorage.setItem('mi_token', 'tok')
    const saved = [
      { id: 4, title: 'Backend Engineer', summary: 'Stakeholder-heavy role.', share_token: 'abc123', saved_at: '2026-10-10T06:00:00Z' },
      { id: 5, title: 'Data Analyst', summary: 'SQL all day.', share_token: 'def456', saved_at: '2026-10-09T06:00:00Z' },
    ]
    const calls = respond({
      'GET /api/auth/me': [200, { user: { id: 1, name: 'Ada', email: 'ada@example.com' } }],
      'GET /api/decoder/saved': [200, { saved }],
      'GET /api/decoder/abc123': [200, { decode: DECODE }],
      'DELETE /api/decoder/saved/5': [204, {}],
    })
    renderAt('/decoder')
    expect(await screen.findByText('Your saved decodes')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Delete Data Analyst' }))
    await userEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(screen.queryByText('Data Analyst')).not.toBeInTheDocument())
    expect(calls.some((c) => c.key === 'DELETE /api/decoder/saved/5')).toBe(true)
    await userEvent.click(screen.getAllByRole('link', { name: 'Open' })[0])
    expect(await screen.findByText('Interpretation, not fact.')).toBeInTheDocument()
    expect(screen.getByText('Keeping stakeholders aligned')).toBeInTheDocument()
  })

  it('shows the daily-cap message', async () => {
    respond({ 'POST /api/decoder': [429, { error: "That's today's free decodes. Sign up (free) to decode more job descriptions." }] })
    renderAt('/decode')
    await paste(await screen.findByLabelText('Job description'), POSTING)
    await userEvent.click(screen.getByRole('button', { name: 'Decode this job' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign up (free)')
  })
})
