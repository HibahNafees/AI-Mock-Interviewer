import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

vi.mock('../lib/monaco', () => ({
  default: ({ value, onChange }) => (
    <textarea aria-label="Monaco" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const EVALUATION = {
  score: 3.4,
  criteria: [{ name: 'API design', score: 4, comment: 'Clear ownership.' }],
  summary: 'Good ownership; the result was missing.',
  weak_moments: [{ quote: 'kind of helped', why: 'Hedges your role.' }],
  star: { situation: true, task: true, action: true, result: false, note: 'No result.' },
  tips: ['Name the scale.'],
  missing_points: [
    { point: 'A measurable result', covered: false },
    { point: 'Their own role', covered: true },
  ],
  stronger_version: 'I built the billing API [add the result you achieved].',
  changes: [{ kind: 'added', text: 'A result', reason: 'Shows impact.' }],
  delivery: null,
}
const DELIVERY = {
  words: 9,
  duration_sec: 75,
  budget_sec: 180,
  spoken: true,
  wpm: 140,
  fillers: { um: 2 },
  filler_total: 2,
  fillers_per_min: 1.6,
  tips: [],
}
const QUESTION = {
  question_id: 3,
  section: 'Background',
  module: 'behavioral',
  text: 'Tell me about Acme.',
  is_bonus: false,
  budget_sec: 180,
  exchange: [{ interviewer: 'Hi Ada! Tell me about Acme.', answer: 'Um, I kind of helped build billing.', is_follow_up: false, input_mode: 'voice' }],
  delivery: DELIVERY,
  evaluation: EVALUATION,
  attempts: [],
}
const READY = {
  session_id: 7,
  status: 'ready',
  role_title: 'Backend Engineer',
  duration_min: 10,
  difficulty: 'mid',
  licensed_field: false,
  overall_score: 3.4,
  verdict: 'lean hire',
  verdict_reason: 'Solid ownership, but results were missing.',
  takeaways: ['Quantify results.', 'Lead with the point.', 'Keep answers tight.'],
  analytics: { questions: 1, answer_sec: 75, budget_sec: 180, avg_wpm: 140, fillers: { um: 2 }, filler_total: 2, over_budget: 0 },
  progress: { scored: 1, total: 1 },
  questions: [QUESTION],
}

function respond(routes) {
  const fetch = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method || 'GET'} ${url}`
    const hit = Object.entries(routes).find(([k]) => key === k)
    if (!hit) throw new Error(`unexpected ${key}`)
    const [status, body] = typeof hit[1] === 'function' ? hit[1](opts) : hit[1]
    return { ok: status < 400, status, json: async () => body }
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
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

describe('report', () => {
  it('builds the report on first visit and shows scores, rewrites and takeaways', async () => {
    const fetch = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [404, { error: 'No report yet' }],
      'POST /api/sessions/7/report': [202, { report: READY }],
    })
    renderAt('/report/7')

    expect(await screen.findByText('Top 3 takeaways')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/sessions/7/report', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByText('Lean hire')).toBeInTheDocument()
    expect(screen.getByText('Quantify results.')).toBeInTheDocument()
    expect(screen.getByText(/not a hiring assessment/)).toBeInTheDocument()
    expect(screen.getByLabelText('Score 3.4 out of 5')).toBeInTheDocument()

    // The weak moment is highlighted inside the transcript, with the reason as a tooltip.
    const said = screen.getByText('What you said').parentElement
    const mark = within(said).getByText('kind of helped')
    expect(mark.tagName).toBe('MARK')
    expect(mark).toHaveAttribute('title', 'Hedges your role.')

    expect(screen.getByText('I built the billing API [add the result you achieved].')).toBeInTheDocument()
    expect(screen.getByLabelText('Missing').nextSibling).toHaveTextContent('A measurable result')
    expect(screen.getAllByText('140 wpm')).toHaveLength(2) // summary + question
    expect(screen.getAllByText('um ×2')).toHaveLength(2)
  })

  it('shows the role-play scenario and labels the character lines', async () => {
    const scenario = { character: 'Dana, a skeptical buyer', setting: '', goal: 'book a demo' }
    const roleplay = {
      ...QUESTION,
      module: 'roleplay',
      scenario,
      exchange: [
        { interviewer: 'This looks expensive.', answer: 'What would it need to save you?', is_follow_up: false },
        { interviewer: 'Ten hours a week.', answer: 'We can do that.', is_follow_up: true },
      ],
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: { ...READY, questions: [roleplay] } }],
    })
    renderAt('/report/7')
    expect(
      await screen.findByText('Role-play with Dana, a skeptical buyer. Your goal: book a demo'),
    ).toBeInTheDocument()
    expect(screen.getByText('They said: Ten hours a week.')).toBeInTheDocument()
  })

  it('polls while the report is being built', async () => {
    let polls = 0
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': () => {
        polls += 1
        return polls === 1
          ? [200, { report: { ...READY, status: 'generating', progress: { scored: 0, total: 1 }, questions: [{ ...QUESTION, evaluation: null }] } }]
          : [200, { report: READY }]
      },
    })
    renderAt('/report/7')
    expect(await screen.findByText('Scoring your answers… 0 of 1 questions done.')).toBeInTheDocument()
    expect(await screen.findByText('Top 3 takeaways', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(polls).toBe(2)
  }, 8000)

  it('shows strengths, AI confidence, competencies, exercises and unanswered questions', async () => {
    // docs/INTERVIEWER_RULES.md, Answer Coaching and Final Report (T-41).
    const e = {
      ...EVALUATION,
      strengths: ['Named the system you built.'],
      confidence: 'low',
      confidence_note: 'Part of the answer may have been misheard.',
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [
        200,
        {
          report: {
            ...READY,
            questions: [{ ...QUESTION, evaluation: e }],
            competencies: [{ name: 'API design', kind: 'role', score: 4, questions: 1 }],
            exercises: ['Write three STAR stories that end with a number.'],
            unanswered: [{ text: 'Design a rate limiter.', section: 'Technical', asked: false }],
          },
        },
      ],
    })
    renderAt('/report/7')
    expect(await screen.findByText('What you did well')).toBeInTheDocument()
    expect(screen.getByText('Named the system you built.')).toBeInTheDocument()
    expect(screen.getByText("AI coach's judgment")).toBeInTheDocument()
    expect(screen.getByText('Low confidence')).toBeInTheDocument()
    expect(screen.getByText('Part of the answer may have been misheard.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Competencies' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Recommended exercises' })).toBeInTheDocument()
    expect(screen.getByText('Write three STAR stories that end with a number.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Questions you didn't get to" })).toBeInTheDocument()
    expect(screen.getByText('Design a rate limiter.')).toBeInTheDocument()
  })

  it('shows the composure score for a pressure interview', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [
        200,
        {
          report: {
            ...READY,
            pressure: {
              level: 1,
              start_level: 3,
              label: 'Skeptical',
              time_limit_sec: null,
              composure: { pct: 88, baseline: 3.6, same_job: true, label: 'A small dip under pressure' },
            },
          },
        },
      ],
    })
    renderAt('/report/7')
    expect(await screen.findByText('Composure: 88%')).toBeInTheDocument()
    expect(screen.getByText('A small dip under pressure')).toBeInTheDocument()
    expect(screen.getByText(/Started at level 3, eased to level 1/)).toBeInTheDocument()
  })

  it('shows body language and the code behind an answer', async () => {
    const code = { kind: 'code', language: 'python', content: 'def allow(u): ...' }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [
        200,
        {
          report: {
            ...READY,
            mode: 'negotiation',
            negotiation: { offer: '$80,000', target: '$92,000', company: '' },
            questions: [{ ...QUESTION, exchange: [{ ...QUESTION.exchange[0], work: code }] }],
            body_language: {
              eye_contact_pct: 45,
              upright_pct: 90,
              fidget_pct: 10,
              face_pct: 95,
              answers: 2,
              tips: ['Look at the camera when you make your key points.'],
            },
          },
        },
      ],
    })
    renderAt('/report/7')
    expect(await screen.findByText('Negotiation report')).toBeInTheDocument()
    expect(screen.getByText('Offer $80,000 · your target $92,000')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('Look at the camera when you make your key points.')).toBeInTheDocument()
    expect(screen.getByText('Your code (python)')).toBeInTheDocument()
    expect(screen.getByText('def allow(u): ...')).toBeInTheDocument()
  })

  it('rates the questions you asked them', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [
        200,
        {
          report: {
            ...READY,
            their_questions: {
              summary: 'Ask about the work, not perks.',
              questions: [{ asked: 'What does a typical week look like?', score: 3, comment: 'Fine but generic.', better: 'What would my first project be?' }],
            },
          },
        },
      ],
    })
    renderAt('/report/7')
    expect(await screen.findByText('Your questions for them')).toBeInTheDocument()
    expect(screen.getByText('“What does a typical week look like?”')).toBeInTheDocument()
    expect(screen.getByText('What would my first project be?')).toBeInTheDocument()
  })

  it('drafts a thank-you email to edit and copy', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: READY }],
      'POST /api/sessions/7/thank-you': [200, { email: { subject: 'Thank you for today', body: "Hi [Interviewer's name],\nThanks!" } }],
    })
    renderAt('/report/7')
    await userEvent.click(await screen.findByRole('button', { name: 'Thank-you email' }))
    expect(await screen.findByText('Thank you for today')).toBeInTheDocument()
    expect(screen.getByLabelText('Email body')).toHaveValue("Hi [Interviewer's name],\nThanks!")
    expect(screen.getByRole('link', { name: 'Cheat sheet' })).toHaveAttribute('href', '/report/7/cheatsheet')
  })

  it('offers to finish a partly failed report', async () => {
    let posted = 0
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: { ...READY, status: 'failed', progress: { scored: 0, total: 1 }, questions: [{ ...QUESTION, evaluation: null }] } }],
      'POST /api/sessions/7/report': () => {
        posted += 1
        return [202, { report: READY }]
      },
    })
    renderAt('/report/7')
    expect(await screen.findByText("Couldn't be scored")).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Finish the report' }))
    expect(await screen.findByText('Top 3 takeaways')).toBeInTheDocument()
    expect(posted).toBe(1)
  })

  it('finishes without a question the AI could not score, and says so', async () => {
    // T-105: "Finish the report" used to fail again on the same question forever.
    const second = { ...QUESTION, question_id: 4, text: 'Tell me about Beta.', evaluation: null, set_aside: true }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [
        200,
        { report: { ...READY, progress: { scored: 1, total: 2, set_aside: 1 }, questions: [QUESTION, second] } },
      ],
    })
    renderAt('/report/7')
    expect(await screen.findByText(/1 question couldn't be scored, so the report covers the other/)).toBeInTheDocument()
    expect(screen.getByText(/The AI couldn't score this answer/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Finish the report' })).not.toBeInTheDocument()
  })

  it('marks an answer cut off by the time limit, with the time tip', async () => {
    // T-109
    const cut = {
      ...QUESTION,
      exchange: QUESTION.exchange.map((x) => ({ ...x, cut_off: true })),
      evaluation: { ...EVALUATION, cut_off: true, tips: ['You ran out of time; lead with your main point sooner.'] },
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: { ...READY, questions: [cut] } }],
    })
    renderAt('/report/7')
    expect(await screen.findByText(/Cut off by the time limit/)).toBeInTheDocument()
    expect(screen.getByText('You ran out of time; lead with your main point sooner.')).toBeInTheDocument()
  })

  it('shows the budget error when the report cannot start', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [404, { error: 'No report yet' }],
      'POST /api/sessions/7/report': [429, { error: "This month's AI budget is used up" }],
    })
    renderAt('/report/7')
    expect(await screen.findByRole('alert')).toHaveTextContent('budget is used up')
  })

  it('tries a question again and shows before and after', async () => {
    let sent
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: READY }],
      'POST /api/sessions/7/questions/3/retry': (opts) => {
        sent = JSON.parse(opts.body)
        return [
          201,
          {
            attempt: { attempt_no: 2, answer: sent.text, input_mode: 'text', evaluation: { ...EVALUATION, score: 4.6 } },
            before_score: 3.4,
          },
        ]
      },
    })
    renderAt('/report/7')
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    await userEvent.type(screen.getByLabelText('Your new answer'), 'I led billing and cut failures by 30%.')
    await userEvent.click(screen.getByRole('button', { name: 'Score my new answer' }))

    expect(await screen.findByLabelText('After 4.6 out of 5')).toBeInTheDocument()
    expect(screen.getByLabelText('Before 3.4 out of 5')).toBeInTheDocument()
    expect(sent).toMatchObject({ text: 'I led billing and cut failures by 30%.', input_mode: 'text' })
    expect(sent.duration_ms).toBeGreaterThanOrEqual(0)
  })

  it('tries a coding question again in the editor, starting from the first code', async () => {
    let sent
    const first = { kind: 'code', language: 'go', content: 'func allow() {}' }
    const coding = { ...QUESTION, module: 'coding', exchange: [{ ...QUESTION.exchange[0], work: first }] }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: { ...READY, questions: [coding] } }],
      'POST /api/sessions/7/questions/3/retry': (opts) => {
        sent = JSON.parse(opts.body)
        return [
          201,
          {
            attempt: { attempt_no: 2, answer: sent.text, work: sent.work, input_mode: 'text', evaluation: EVALUATION },
            before_score: 3.4,
          },
        ]
      },
    })
    renderAt('/report/7')
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    const editor = await screen.findByLabelText('Monaco')
    expect(editor).toHaveValue('func allow() {}')
    await userEvent.type(editor, ' // fixed')
    await userEvent.click(screen.getByRole('button', { name: 'Score my new answer' }))
    await screen.findByText('(attempt 2)')
    expect(sent).toMatchObject({
      text: '(My answer is in the code editor.)',
      work: { kind: 'code', language: 'go', content: 'func allow() {} // fixed' },
    })
  })

  it('creates, copies and turns off a read-only share link', async () => {
    const user = userEvent.setup()
    const fetch = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7/report': [200, { report: READY }],
      'POST /api/sessions/7/report/share': [200, { share_token: 'abc123' }],
      'DELETE /api/sessions/7/report/share': [200, { ok: true }],
    })
    renderAt('/report/7')
    await user.click(await screen.findByRole('button', { name: 'Create a read-only link' }))
    expect(await screen.findByLabelText('Share link')).toHaveValue(`${window.location.origin}/shared/abc123`)
    await user.click(screen.getByRole('button', { name: 'Turn off link' }))
    expect(await screen.findByText('The link is turned off.')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/sessions/7/report/share', expect.objectContaining({ method: 'DELETE' }))
  })

  it('shows a shared report read-only without logging in', async () => {
    localStorage.removeItem('mi_token')
    respond({ 'GET /api/shared/reports/abc123': [200, { report: { ...READY, shared: true } }] })
    render(
      <MemoryRouter initialEntries={['/shared/abc123']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Shared interview report')).toBeInTheDocument()
    expect(screen.getByText('Top 3 takeaways')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Try again/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Transcript')).not.toBeInTheDocument()
    expect(screen.queryByText('Share this report')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign up free' })).toBeInTheDocument()
  })

  it('says when a shared link was turned off', async () => {
    localStorage.removeItem('mi_token')
    respond({ 'GET /api/shared/reports/gone': [404, { error: 'This link was turned off or never existed' }] })
    render(
      <MemoryRouter initialEntries={['/shared/gone']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('turned off')
  })
})
