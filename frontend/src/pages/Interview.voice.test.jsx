import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'
import { FILLERS } from '../lib/voice'
import { fakeSpeech } from '../test-speech'

// Stand-in recorder: one click "records" a 4.2-second clip.
vi.mock('../components/Recorder', () => ({
  default: ({ onRecorded, disabled, autoStartKey = 0 }) => (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onRecorded(new Blob(['clip'], { type: 'audio/webm;codecs=opus' }), 4200)}
      >
        Record answer
      </button>
      <span data-testid="auto-record">{autoStartKey}</span>
    </>
  ),
}))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const FIRST = {
  question_id: 1,
  interviewer: 'Tell me about Acme.',
  segments: [{ who: 'interviewer', text: 'Tell me about Acme.' }],
  answer: null,
}
const TURN = {
  action: 'follow_up',
  message: 'What was your part?',
  segments: [{ who: 'interviewer', text: 'What was your part?' }],
}
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
          turn: TURN,
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
          : [200, { turn: TURN, session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }] } }],
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

describe('interviewer voice', () => {
  const NEXT = { question_id: 2, interviewer: 'What was your part?', segments: TURN.segments, answer: null }
  const ANSWERED = { ...FIRST, answer: 'I led the billing API.', input_mode: 'voice' }

  function routes(extra = {}, session = ACTIVE) {
    return respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        { turn: TURN, session: { ...session, transcript: [ANSWERED, NEXT] }, speech: null },
      ],
      ...extra,
    })
  }

  it('says "Mm-hm" while the reply is written, then speaks the reply', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')

    const said = spoken.map((u) => u.text)
    expect(FILLERS).toContain(said[0])
    expect(said.at(-1)).toBe('What was your part?')
    expect(screen.getByText('Interviewer is speaking…')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(screen.queryByText('Interviewer is speaking…')).not.toBeInTheDocument()
  })

  it('can be turned off, and stays off', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByLabelText('Interviewer voice'))
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    expect(spoken).toEqual([])
    expect(localStorage.getItem('mi_voice')).toBe('off')

    // "Repeat" still reads the question out on request.
    await userEvent.click(screen.getByRole('button', { name: 'Repeat the question' }))
    expect(spoken.map((u) => u.text)).toEqual(['What was your part?'])
  })

  it('repeats the current question after a reload', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Repeat the question' }))
    expect(spoken.map((u) => u.text)).toEqual(['Tell me about Acme.'])
  })

  it('says so when the browser cannot speak', async () => {
    const spoken = fakeSpeech([])
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Repeat the question' }))
    spoken[0].onerror({ error: 'synthesis-failed' })
    expect(await screen.findByText(/couldn't play the interviewer's voice/)).toBeInTheDocument()
  })

  it('has no voice controls without speech support', async () => {
    routes()
    renderInterview()
    await screen.findByRole('button', { name: 'Record answer' })
    expect(screen.queryByLabelText('Interviewer voice')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Repeat the question' })).not.toBeInTheDocument()
  })

  it('plays Fire audio when the backend sends it', async () => {
    fakeSpeech()
    const played = []
    vi.stubGlobal('Audio', class {
      constructor(src) {
        played.push(src)
      }
      play() {
        return Promise.resolve()
      }
      pause() {}
    })
    const fire = { ...ACTIVE, voice: { provider: 'fire', persona: 'neutral' } }
    const clip = { who: 'interviewer', audio: 'data:audio/mpeg;base64,AA' }
    const calls = routes(
      {
        'POST /api/sessions/7/turns': [
          200,
          { turn: TURN, session: { ...fire, transcript: [ANSWERED, NEXT] }, speech: [clip] },
        ],
      },
      fire,
    )
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await vi.waitFor(() => expect(played).toEqual([clip.audio]))
    const turn = calls.find((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turn.opts.body).speak).toBe(true)
  })

  it('shows and speaks the closing line', async () => {
    const spoken = fakeSpeech()
    const closing = 'That covers everything. Thank you.'
    routes({
      'POST /api/sessions/7/turns': [
        200,
        {
          turn: { action: 'wrap_up', message: closing, segments: [{ who: 'interviewer', text: closing }] },
          session: { ...ACTIVE, status: 'completed', transcript: [ANSWERED] },
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    expect(await screen.findByText(closing)).toBeInTheDocument()
    expect(spoken.map((u) => u.text).slice(-2)).toEqual(['That covers everything.', 'Thank you.'])
  })
})

describe('auto-record', () => {
  const NEXT = { question_id: 2, interviewer: 'What was your part?', segments: TURN.segments, answer: null }
  function routes() {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        { turn: TURN, session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }, NEXT] } },
      ],
    })
  }

  it('starts recording when the interviewer finishes the next question', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    expect(screen.getByTestId('auto-record')).toHaveTextContent('0') // still speaking
    await act(async () => spoken.at(-1).onend())
    expect(screen.getByTestId('auto-record')).toHaveTextContent('1')
  })

  it('starts right away when the interviewer voice is off', async () => {
    fakeSpeech()
    localStorage.setItem('mi_voice', 'off')
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await vi.waitFor(() => expect(screen.getByTestId('auto-record')).toHaveTextContent('1'))
  })

  it('opens in typing mode when that was chosen', async () => {
    localStorage.setItem('mi_answer_mode', 'text')
    routes()
    renderInterview()
    expect(await screen.findByLabelText('Your answer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speak instead' }))
    expect(localStorage.getItem('mi_answer_mode')).toBe('voice')
  })
})

describe('your questions', () => {
  it('shows a hint when the interviewer invites questions', async () => {
    const invite = {
      question_id: 9,
      section: 'Your questions',
      interviewer: 'Before we wrap up, do you have any questions for me?',
      segments: [{ who: 'interviewer', text: 'Before we wrap up, do you have any questions for me?' }],
      answer: null,
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }, invite] } }],
    })
    renderInterview()
    expect(await screen.findByText('Your turn to ask.')).toBeInTheDocument()
  })
})
