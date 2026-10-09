import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

// Stand-in recorder: one click "records" a 4.2-second clip.
vi.mock('../components/Recorder', () => ({
  default: ({ onRecorded, disabled }) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onRecorded(new Blob(['clip'], { type: 'audio/webm;codecs=opus' }), 4200)}
    >
      Record answer
    </button>
  ),
}))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const FIRST = { question_id: 1, interviewer: 'Tell me about Acme.', answer: null }
const ACTIVE = {
  id: 7,
  status: 'active',
  role_title: 'Backend Engineer',
  duration_min: 10,
  timer: { remaining_sec: 600, section: 'Background', section_remaining_sec: 240 },
  transcript: [FIRST],
}

function respond(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      calls.push({ key: `${opts.method || 'GET'} ${url}`, opts })
      const handler = routes[`${opts.method || 'GET'} ${url}`]
      if (!handler) throw new Error(`unexpected ${url}`)
      const [status, body] = typeof handler === 'function' ? handler(opts) : handler
      return { ok: status < 400, status, json: async () => body }
    }),
  )
  return calls
}

function renderInterview() {
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={['/interview/7']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('MediaRecorder', class {})
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn() },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('spoken answers', () => {
  it('transcribes the clip, then sends the text as a voice turn', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        {
          session: {
            ...ACTIVE,
            transcript: [
              { ...FIRST, answer: 'I led the billing API.', input_mode: 'voice' },
              { question_id: 2, interviewer: 'What was your part?', answer: null },
            ],
          },
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))

    expect(await screen.findByText('What was your part?')).toBeInTheDocument()
    expect(screen.getByText('I led the billing API.')).toBeInTheDocument()
    expect(screen.getByText('You · transcribed')).toBeInTheDocument()

    const upload = calls.find((c) => c.key === 'POST /api/sessions/7/transcribe')
    expect(upload.opts.body).toBeInstanceOf(FormData)
    expect(upload.opts.body.get('audio').name).toBe('answer.webm')
    expect(upload.opts.headers['Content-Type']).toBeUndefined()
    const turn = calls.find((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turn.opts.body)).toEqual({
      text: 'I led the billing API.',
      duration_ms: 4200,
      input_mode: 'voice',
    })
  })

  it('keeps the transcript to resend if the interviewer call fails', async () => {
    let attempts = 0
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': () =>
        ++attempts === 1
          ? [429, { error: 'The AI service is busy; please wait a moment' }]
          : [200, { session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }] } }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('busy')
    expect(screen.getByLabelText('Your answer')).toHaveValue('I led the billing API.')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))

    const turns = calls.filter((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turns[1].opts.body)).toEqual({
      text: 'I led the billing API.',
      duration_ms: 4200,
      input_mode: 'voice',
    })
    expect(calls.filter((c) => c.key.endsWith('/transcribe'))).toHaveLength(1)
  })

  it('shows a transcription error and lets the user record again', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [422, { error: "We didn't catch any speech; please try again" }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("didn't catch")
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeEnabled()
  })

  it('can switch to typing', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Type instead' }))
    expect(screen.getByLabelText('Your answer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speak instead' }))
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })
})
