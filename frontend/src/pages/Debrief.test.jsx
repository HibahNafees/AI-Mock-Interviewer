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
    expect(body.items).toEqual([
      {
        question: 'Tell me about yourself.',
        answer: 'I build payment APIs at Acme.',
        input_mode: 'text',
        duration_ms: null,
      },
    ])
    expect(body.company).toBe('Fintech Co')
  })

  it('shows next-round questions and practices them', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/30/report': [200, { report: REPORT }],
      'POST /api/debriefs/4/practice': [201, { session: { id: 31 } }],
      'GET /api/sessions/31': [
        200,
        { session: { id: 31, status: 'planned', plan: { sections: [], reserve: [] }, transcript: [], analysis: {} } },
      ],
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

  it('takes a pasted job description and scores against it', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'GET /api/debriefs': [200, { debriefs: [] }],
      'POST /api/documents': [
        201,
        { document: { id: 9, title: 'Backend role', saved: false, expires_at: '2026-11-11T00:00:00Z' } },
      ],
      'POST /api/debriefs': [201, { debrief: { id: 4, session_id: 30 } }],
      'GET /api/sessions/30/report': [200, { report: REPORT }],
    })
    renderAt('/debrief')
    await userEvent.type(await screen.findByLabelText('Role'), 'Backend Engineer')
    await userEvent.type(screen.getByLabelText('Paste job description'), 'Backend Engineer at a fintech. '.repeat(3))
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    expect(await screen.findByRole('button', { name: 'Save this job posting' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('What they asked'), 'Tell me about yourself.')
    await userEvent.type(screen.getByLabelText(/What you answered/), 'I build payment APIs at Acme.')
    await userEvent.click(screen.getByRole('button', { name: 'Score my debrief' }))
    await screen.findByText('Backend Engineer at Fintech Co')
    const body = JSON.parse(calls.find((c) => c.key === 'POST /api/debriefs').opts.body)
    expect(body.jd_id).toBe(9)
  })

  it('deletes a past debrief', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'GET /api/debriefs': [200, { debriefs: [REPORT.debrief] }],
      'DELETE /api/debriefs/4': [200, { ok: true }],
    })
    renderAt('/debrief')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete the debrief Backend Engineer' }))
    await vi.waitFor(() => expect(screen.queryByText('Past debriefs')).not.toBeInTheDocument())
    expect(calls.some((c) => c.key === 'DELETE /api/debriefs/4')).toBe(true)
    window.confirm.mockRestore()
  })

  it('after a debrief: save its job posting or delete the debrief', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const jd = { id: 9, title: 'Backend role', saved: false }
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/30/report': [200, { report: { ...REPORT, debrief: { ...REPORT.debrief, jd } } }],
      'POST /api/documents/9/save': [200, { document: { ...jd, saved: true } }],
      'DELETE /api/debriefs/4': [200, { ok: true }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'GET /api/debriefs': [200, { debriefs: [] }],
    })
    renderAt('/report/30')
    await userEvent.click(await screen.findByRole('button', { name: 'Save job posting' }))
    expect(await screen.findByText(/saved until you delete it/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete job posting' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Delete debrief' }))
    expect(await screen.findByText('How did the real one go?')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'DELETE /api/debriefs/4')).toBe(true)
    window.confirm.mockRestore()
  })
})
