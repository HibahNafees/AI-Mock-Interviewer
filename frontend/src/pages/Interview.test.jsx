import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const TIMER = {
  total_sec: 600,
  elapsed_sec: 0,
  remaining_sec: 600,
  section: 'Background',
  section_budget_sec: 240,
  section_elapsed_sec: 0,
  section_remaining_sec: 240,
}
const PLANNED = {
  id: 7,
  status: 'planned',
  role_title: 'Backend Engineer',
  duration_min: 10,
  difficulty: 'mid',
  persona: 'friendly',
  analysis: { competencies: [{ name: 'API design' }], licensed_field: false },
  plan: {
    sections: [
      { name: 'Background', module: 'resume_deepdive', minutes: 4, questions: ['Tell me about Acme.'] },
      { name: 'Technical', module: 'technical', minutes: 6, questions: ['Design a rate limiter.'] },
    ],
    reserve: [],
  },
  transcript: [],
  timer: null,
}
const FIRST = { question_id: 1, interviewer: 'Hi Ada! Tell me about Acme.', answer: null }

function respond(routes) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      const hit = Object.entries(routes).find(([k]) => key === k)
      if (!hit) throw new Error(`unexpected ${key}`)
      const [status, body] = typeof hit[1] === 'function' ? hit[1](opts) : hit[1]
      return { ok: status < 400, status, json: async () => body }
    }),
  )
}

function renderAt(path) {
  localStorage.setItem('mi_token', 'tok')
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('setup', () => {
  it('pastes documents and builds a plan', async () => {
    let created
    let nextDoc = 10
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [] }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'POST /api/documents': (opts) => {
        const body = JSON.parse(opts.body)
        return [201, { document: { id: nextDoc++, kind: body.kind, title: body.kind } }]
      },
      'POST /api/sessions': (opts) => {
        created = JSON.parse(opts.body)
        return [201, { session: PLANNED }]
      },
      'GET /api/sessions/7': [200, { session: PLANNED }],
    })
    renderAt('/setup')
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    await userEvent.click(screen.getByRole('radio', { name: '30 min' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Tough' }))
    await userEvent.click(screen.getByRole('button', { name: 'Build my interview plan' }))

    expect(await screen.findByText('Your interview plan')).toBeInTheDocument()
    expect(created).toEqual({
      resume_id: 10,
      jd_id: 11,
      duration_min: 30,
      difficulty: 'mid',
      persona: 'tough',
    })
  })
})

describe('interview', () => {
  it('edits the plan, starts, and answers by typing', async () => {
    let savedPlan
    let sentTurn
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: PLANNED }],
      'PUT /api/sessions/7/plan': (opts) => {
        savedPlan = JSON.parse(opts.body)
        return [200, { session: { ...PLANNED, plan: savedPlan } }]
      },
      'POST /api/sessions/7/start': [
        200,
        { session: { ...PLANNED, status: 'active', transcript: [FIRST], timer: TIMER } },
      ],
      'POST /api/sessions/7/turns': (opts) => {
        sentTurn = JSON.parse(opts.body)
        return [
          200,
          {
            turn: { action: 'follow_up' },
            session: {
              ...PLANNED,
              status: 'active',
              timer: TIMER,
              transcript: [
                { ...FIRST, answer: sentTurn.text },
                { question_id: 2, interviewer: 'What was your part?', is_follow_up: true, answer: null },
              ],
            },
          },
        ]
      },
    })
    renderAt('/interview/7')

    const minutes = await screen.findByLabelText('Section 1 minutes')
    await userEvent.clear(minutes)
    await userEvent.type(minutes, '5')
    expect(screen.getByText('Sections total 11 of 10 minutes.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    const second = screen.getByLabelText('Section 2 minutes')
    await userEvent.clear(second)
    await userEvent.type(second, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(savedPlan.sections.map((s) => s.minutes)).toEqual([5, 5])

    await userEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    expect(await screen.findByText('Hi Ada! Tell me about Acme.')).toBeInTheDocument()
    expect(screen.getByLabelText('Time left')).toHaveTextContent('10:00')

    await userEvent.type(screen.getByLabelText('Your answer'), 'I led the billing API.')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    expect(await screen.findByText('What was your part?')).toBeInTheDocument()
    expect(sentTurn.text).toBe('I led the billing API.')
    expect(sentTurn.duration_ms).toBeGreaterThanOrEqual(0)
    expect(screen.getByLabelText('Your answer')).toHaveValue('')
  })

  it('keeps the typed answer when the server fails', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [
        200,
        { session: { ...PLANNED, status: 'active', transcript: [FIRST], timer: TIMER } },
      ],
      'POST /api/sessions/7/turns': [429, { error: 'The AI service is busy; please wait a moment' }],
    })
    renderAt('/interview/7')
    await userEvent.type(await screen.findByLabelText('Your answer'), 'My answer')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('busy')
    expect(screen.getByLabelText('Your answer')).toHaveValue('My answer')
  })

  it('shows the finished state', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [
        200,
        { session: { ...PLANNED, status: 'completed', transcript: [{ ...FIRST, answer: 'Done' }] } },
      ],
    })
    renderAt('/interview/7')
    expect(await screen.findByText('Interview finished.')).toBeInTheDocument()
    const you = screen.getByText('Done').closest('div')
    expect(within(you).getByText('You')).toBeInTheDocument()
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument()
  })
})
