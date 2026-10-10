import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }

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

afterEach(() => vi.unstubAllGlobals())

const REPORT = {
  session_id: 30,
  status: 'ready',
  role_title: 'Backend Engineer',
  duration_min: 6,
  difficulty: 'mid',
  licensed_field: false,
  overall_score: 3.2,
  verdict: 'lean hire',
  verdict_reason: 'Good start.',
  takeaways: ['Quantify results.'],
  exercises: [],
  competencies: [],
  unanswered: [],
  analytics: null,
  progress: { scored: 0, total: 0 },
  questions: [],
  debrief: {
    id: 4,
    role: 'Backend Engineer',
    company: 'Fintech Co',
    round: 'Phone screen',
    session_id: 30,
    items: 2,
    next_round: [{ question: 'Walk me through a schema you designed.', why: 'MySQL came up', module: 'technical' }],
  },
}

describe('debrief', () => {
  it('explains no recordings, collects recall and opens the scored report', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'GET /api/debriefs': [200, { debriefs: [] }],
      'POST /api/debriefs': [201, { debrief: { id: 4, session_id: 30 } }],
      'GET /api/sessions/30/report': [200, { report: REPORT }],
    })
    renderAt('/debrief')
    expect(await screen.findByText('Recall only, never recordings.')).toBeInTheDocument()
    expect(document.querySelector('input[type=file]')).toBeNull()
    await userEvent.type(screen.getByLabelText('Role'), 'Backend Engineer')
    await userEvent.type(screen.getByLabelText(/Company/), 'Fintech Co')
    await userEvent.type(screen.getByLabelText('What they asked'), 'Tell me about yourself.')
    await userEvent.type(screen.getByLabelText(/What you answered/), 'I build payment APIs at Acme.')
    await userEvent.click(screen.getByRole('button', { name: '+ Add another question' }))
    await userEvent.click(screen.getByRole('button', { name: 'Score my debrief' }))
    expect(await screen.findByText('Backend Engineer at Fintech Co')).toBeInTheDocument()
    const body = JSON.parse(calls.find((c) => c.key === 'POST /api/debriefs').opts.body)
    expect(body.items).toEqual([{ question: 'Tell me about yourself.', answer: 'I build payment APIs at Acme.', input_mode: 'text', duration_ms: null }])
    expect(body.company).toBe('Fintech Co')
  })

  it('shows next-round questions and practices them', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/30/report': [200, { report: REPORT }],
      'POST /api/debriefs/4/practice': [201, { session: { id: 31 } }],
      'GET /api/sessions/31': [200, { session: { id: 31, status: 'planned', plan: { sections: [], reserve: [] }, transcript: [], analysis: {} } }],
    })
    renderAt('/report/30')
    expect(await screen.findByText('Walk me through a schema you designed.')).toBeInTheDocument()
    expect(screen.getByText('Recall only, never recordings.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Practice the next round' }))
    expect(await screen.findByText('Your interview plan')).toBeInTheDocument()
  })

  it('can retry a missing prediction', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/30/report': [200, { report: { ...REPORT, debrief: { ...REPORT.debrief, next_round: [] } } }],
      'POST /api/debriefs/4/predict': [200, { debrief: REPORT.debrief }],
    })
    renderAt('/report/30')
    await userEvent.click(await screen.findByRole('button', { name: 'Predict the next round' }))
    expect(await screen.findByText('Walk me through a schema you designed.')).toBeInTheDocument()
  })
})
