import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'
import { fakeSpeech } from '../test-speech'

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
      'POST /api/documents/11/analysis': [
        200,
        {
          analysis: { role_title: 'Backend Engineer', field: 'software', competencies: [{ name: 'API design' }] },
          modules: [
            { name: 'behavioral', label: 'Behavioral', blurb: 'Stories' },
            { name: 'technical', label: 'Technical Q&A', blurb: 'Knowledge questions for the field' },
          ],
        },
      ],
      'GET /api/sessions/7': [200, { session: PLANNED }],
    })
    renderAt('/setup')
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    // Only interview types that fit the job are offered; mixed is the default.
    const types = await screen.findByRole('radiogroup', { name: 'Interview type' })
    expect(within(types).getAllByRole('radio').map((r) => r.textContent)).toEqual([
      'Full mixed loop',
      'Behavioral',
      'Technical Q&A',
    ])
    expect(within(types).getByRole('radio', { name: 'Full mixed loop' })).toBeChecked()
    await userEvent.click(within(types).getByRole('radio', { name: 'Technical Q&A' }))
    expect(screen.getByText('Knowledge questions for the field')).toBeInTheDocument()
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
      focus: 'technical',
      pressure_level: 0,
      format: 'standard',
    })
  })
})

const SCENARIO = {
  character: 'Dana, an operations manager who thinks the price is too high',
  setting: 'A video call after your demo',
  goal: 'book a follow-up meeting',
}
const ROLEPLAY = {
  ...PLANNED,
  role_title: 'Account Executive',
  plan: {
    sections: [
      { name: 'Sales call', module: 'roleplay', minutes: 10, questions: ['This looks expensive.'], scenario: SCENARIO },
    ],
    reserve: [],
  },
}

describe('setup choices', () => {
  it('can start right away, answering by typing', async () => {
    let started = false
    const active = { ...PLANNED, status: 'active', transcript: [FIRST], timer: TIMER }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [{ id: 1, title: 'CV' }] }],
      'GET /api/documents?kind=job_description': [200, { documents: [{ id: 2, title: 'Job' }] }],
      'POST /api/documents/2/analysis': [
        200,
        { analysis: { role_title: 'Backend Engineer', field: 'software', competencies: [] }, modules: [] },
      ],
      'POST /api/sessions': [201, { session: PLANNED }],
      'POST /api/sessions/7/start': () => {
        started = true
        return [200, { session: active, speech: null }]
      },
      'GET /api/sessions/7': () => [200, { session: started ? active : PLANNED }],
    })
    renderAt('/setup')
    await screen.findByRole('radiogroup', { name: 'Interview type' })
    await userEvent.click(screen.getByRole('radio', { name: 'Start right away' }))
    await userEvent.click(screen.getByRole('radio', { name: '⌨️ Typing' }))
    await userEvent.click(screen.getByRole('button', { name: 'Start my interview' }))

    // Straight to the first question: no plan screen.
    expect(await screen.findByText('Hi Ada! Tell me about Acme.')).toBeInTheDocument()
    expect(started).toBe(true)
    expect(screen.queryByText('Your interview plan')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Your answer')).toBeInTheDocument()
    expect(localStorage.getItem('mi_answer_mode')).toBe('text')
  })
})

describe('role-play', () => {
  it('shows the scenario in the plan, then who is speaking during the call', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ROLEPLAY }],
      'POST /api/sessions/7/start': [
        200,
        {
          session: {
            ...ROLEPLAY,
            status: 'active',
            timer: { ...TIMER, section: 'Sales call' },
            transcript: [
              {
                question_id: 1,
                section: 'Sales call',
                interviewer: "Let's switch to a role-play. This looks expensive.",
                segments: [
                  { who: 'interviewer', text: "Let's switch to a role-play." },
                  { who: 'character', text: 'This looks expensive.' },
                ],
                answer: 'What would it need to save you?',
              },
              { question_id: 2, section: 'Sales call', is_follow_up: true, interviewer: 'About ten hours a week.', answer: null },
            ],
          },
        },
      ],
    })
    renderAt('/interview/7')
    expect(await screen.findByText('Role-play')).toBeInTheDocument()
    expect(screen.getByText(SCENARIO.character)).toBeInTheDocument()
    expect(screen.getByText(SCENARIO.goal)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Start interview' }))
    // The app's announcement and the character's line are separate bubbles.
    expect(await screen.findByText("Let's switch to a role-play.")).toBeInTheDocument()
    expect(screen.getByText('This looks expensive.')).toBeInTheDocument()
    expect(screen.getAllByText('Dana · role-play')).toHaveLength(2)
    expect(screen.getByText(/the interviewer is playing/)).toHaveTextContent(
      `Role-play: the interviewer is playing ${SCENARIO.character}. Your goal: ${SCENARIO.goal}`,
    )
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
            turn: {
              action: 'follow_up',
              message: 'What was your part?',
              segments: [{ who: 'interviewer', text: 'What was your part?' }],
            },
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

  it('speaks the first question when the interview starts', async () => {
    const spoken = fakeSpeech()
    const segments = [
      { who: 'interviewer', text: 'Hi Ada!' },
      { who: 'character', text: 'Tell me about Acme.' },
    ]
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: PLANNED }],
      'POST /api/sessions/7/start': [
        200,
        { session: { ...PLANNED, status: 'active', transcript: [{ ...FIRST, segments }], timer: TIMER } },
      ],
    })
    renderAt('/interview/7')
    await userEvent.click(await screen.findByRole('button', { name: 'Start interview' }))
    await screen.findByText('Tell me about Acme.')
    expect(spoken.map((u) => [u.text, u.voice.name])).toEqual([
      ['Hi Ada!', 'Alex'],
      ['Tell me about Acme.', 'Sam'],
    ])
  })
})
