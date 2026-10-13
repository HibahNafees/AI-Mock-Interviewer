import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'
import { fakeSpeech } from '../test-speech'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const CANDIDATE = { name: 'Sam', headline: 'Backend engineer, 4 years', resume: ['Led the payments API rewrite'] }
const OPEN = { id: 9, status: 'active', role_title: 'Backend Engineer', duration_min: 10, candidate: CANDIDATE, transcript: [], max_questions: 15, reveal: null }
const QA = { question: 'Who led the rewrite?', answer: 'Well, I was part of the team that did it.', input_mode: 'text' }
const REVEAL = {
  profile: 'exaggerating',
  hidden: { truths: ['Joined the rewrite late'], exaggerations: ['Did not lead the rewrite'], strengths: [], weaknesses: [], answer_style: '' },
  result: {
    decision: 'no_hire',
    reasons: 'Could not say what they led.',
    expected: 'no_hire',
    decision_matches: true,
    judgment: { score: 5, comment: 'Probed the claim and caught it.' },
    questioning: { score: 4, comment: 'Good follow-ups.' },
    question_feedback: [{ question: 'Who led the rewrite?', score: 5, comment: 'Exactly the right probe.' }],
    missed_signals: [],
    good_moves: ['Asked who led it.'],
    unfair_questions: [],
    tips: ['Ask for numbers too.'],
  },
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

describe('reverse mode', () => {
  it('sets up a secret candidate for a saved job', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [{ id: 2, title: 'Backend job' }] }],
      'POST /api/reverse': [201, { reverse: OPEN }],
      'GET /api/reverse/9': [200, { reverse: OPEN }],
    })
    renderAt('/reverse')
    await userEvent.click(await screen.findByRole('radio', { name: 'Exaggerates their résumé' }))
    await userEvent.click(screen.getByRole('button', { name: 'Meet the candidate' }))
    expect(await screen.findByText('Led the payments API rewrite')).toBeInTheDocument()
    expect(JSON.parse(calls.find((c) => c.key === 'POST /api/reverse').opts.body)).toEqual({ jd_id: 2, profile: 'exaggerating', duration_min: 10 })
  })

  it('asks questions, decides, and reveals the hidden profile', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/reverse/9': [200, { reverse: OPEN }],
      'POST /api/reverse/9/ask': [200, { reverse: { ...OPEN, transcript: [QA] } }],
      'POST /api/reverse/9/decide': [200, { reverse: { ...OPEN, status: 'completed', transcript: [QA], reveal: REVEAL } }],
    })
    renderAt('/reverse/9')
    await userEvent.type(await screen.findByLabelText('Your question'), 'Who led the rewrite?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Well, I was part of the team that did it.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Make your decision' }))
    await userEvent.click(screen.getByRole('radio', { name: 'No hire' }))
    await userEvent.type(screen.getByLabelText(/Why\?/), 'Could not say what they led.')
    await userEvent.click(screen.getByRole('button', { name: 'Reveal the candidate' }))
    expect(await screen.findByText('Sam was exaggerating their résumé')).toBeInTheDocument()
    expect(screen.getByText('Did not lead the rewrite')).toBeInTheDocument()
    expect(screen.getByText('That matches what a careful interviewer would decide.', { exact: false })).toBeInTheDocument()
    expect(screen.queryByLabelText('Your question')).not.toBeInTheDocument()
  })

  it("speaks the candidate's answers in the character voice, with an off switch (T-133)", async () => {
    const spoken = fakeSpeech()
    const QA2 = { question: 'What did you own?', answer: 'The retry logic, mostly.', input_mode: 'text' }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/reverse/9': [200, { reverse: OPEN }],
      'POST /api/reverse/9/ask': (opts) => [
        200,
        { reverse: { ...OPEN, transcript: JSON.parse(opts.body).text === QA.question ? [QA] : [QA, QA2] } },
      ],
    })
    renderAt('/reverse/9')
    await userEvent.type(await screen.findByLabelText('Your question'), QA.question)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText(QA.answer)
    // The second system voice, not the interviewer's.
    expect(spoken.map((u) => [u.text, u.voice.name])).toEqual([['Well, I was part of the team that did it.', 'Sam']])
    await userEvent.click(screen.getByRole('button', { name: 'Stop talking' }))
    expect(window.speechSynthesis.cancel).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Stop talking' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox', { name: 'Candidate voice' }))
    expect(localStorage.getItem('mi_voice')).toBe('off')
    await userEvent.type(screen.getByLabelText('Your question'), QA2.question)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText(QA2.answer)
    expect(spoken).toHaveLength(1)
    localStorage.removeItem('mi_voice')
  })

  it('asks for a job description first', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
    })
    renderAt('/reverse')
    expect(await screen.findByText(/Add a job description first/)).toBeInTheDocument()
  })

  it('offers a custom length', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=job_description': [200, { documents: [{ id: 2, title: 'Backend job' }] }],
      'POST /api/reverse': [201, { reverse: OPEN }],
      'GET /api/reverse/9': [200, { reverse: OPEN }],
    })
    renderAt('/reverse')
    await userEvent.click(await screen.findByRole('radio', { name: 'Custom' }))
    const slider = screen.getByLabelText('Custom length in minutes')
    expect(slider).toHaveAttribute('min', '5')
    expect(slider).toHaveAttribute('max', '30')
    fireEvent.change(slider, { target: { value: '15' } })
    expect(screen.getByText('15 minutes')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Meet the candidate' }))
    await screen.findByText('Led the payments API rewrite')
    expect(JSON.parse(calls.find((c) => c.key === 'POST /api/reverse').opts.body).duration_min).toBe(15)
  })

  it('counts down and nudges a decision when time is up', async () => {
    const started = new Date(Date.now() - 3 * 60_000).toISOString()
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/reverse/9': [200, { reverse: { ...OPEN, started_at: started, duration_min: 15 } }],
    })
    renderAt('/reverse/9')
    expect(await screen.findByLabelText('Time left')).toHaveTextContent('12 min left of 15')
    expect(screen.queryByText("Time's up.")).not.toBeInTheDocument()
  })

  it("says when time's up", async () => {
    const started = new Date(Date.now() - 20 * 60_000).toISOString()
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/reverse/9': [200, { reverse: { ...OPEN, started_at: started, duration_min: 10, transcript: [QA] } }],
    })
    renderAt('/reverse/9')
    expect(await screen.findByText("Time's up.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make your decision' })).toBeEnabled()
  })
})
