import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

// Monaco and Excalidraw need a real browser: stand-ins with the same props.
vi.mock('../lib/monaco', () => ({
  default: ({ value, onChange }) => (
    <textarea aria-label="Monaco" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))
vi.mock('../components/Whiteboard', () => ({
  default: ({ onChange }) => (
    <button
      type="button"
      onClick={() =>
        onChange([
          { id: 'a', type: 'rectangle' },
          { id: 't', type: 'text', text: 'API', containerId: 'a' },
          { id: 'b', type: 'rectangle' },
          { id: 'u', type: 'text', text: 'Redis', containerId: 'b' },
          { id: 'x', type: 'arrow', startBinding: { elementId: 'a' }, endBinding: { elementId: 'b' } },
        ])
      }
    >
      Draw
    </button>
  ),
}))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const PLAN = {
  sections: [
    { name: 'Coding', module: 'coding', minutes: 6, questions: ['Rate-limit each user.'] },
    { name: 'Design', module: 'system_design', minutes: 4, questions: ['Design it for many servers.'] },
  ],
  reserve: [],
}
const TIMER = {
  total_sec: 600,
  elapsed_sec: 0,
  remaining_sec: 600,
  section: 'Coding',
  section_budget_sec: 360,
  section_elapsed_sec: 0,
  section_remaining_sec: 360,
}
const ask = (id, section, text) => ({ question_id: id, section, interviewer: text, answer: null })
const session = (transcript, section) => ({
  id: 7,
  status: 'active',
  mode: 'standard',
  role_title: 'Backend Engineer',
  duration_min: 10,
  persona: 'neutral',
  plan: PLAN,
  timer: { ...TIMER, section },
  transcript,
})

afterEach(() => vi.unstubAllGlobals())

it('sends the code, then the sketch as text, with the answers', async () => {
  localStorage.setItem('mi_answer_mode', 'text')
  const sent = []
  const first = ask(1, 'Coding', 'Rate-limit each user.')
  const second = ask(2, 'Design', 'Design it for many servers.')
  const replies = [
    session([{ ...first, answer: 'x' }, second], 'Design'),
    session([{ ...first, answer: 'x' }, { ...second, answer: 'y' }, ask(3, 'Design', 'Where do counters live?')], 'Design'),
  ]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      let body
      if (key === 'GET /api/auth/me') body = { user: ADA }
      else if (key === 'GET /api/sessions/7') body = { session: session([first], 'Coding') }
      else if (key === 'POST /api/sessions/7/turns') {
        sent.push(JSON.parse(opts.body))
        body = { turn: { action: 'next_question', segments: [] }, session: replies.shift(), speech: null }
      } else throw new Error(`unexpected ${key}`)
      return { ok: true, status: 200, json: async () => body }
    }),
  )
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={['/interview/7']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
  // Body language stays off unless turned on.
  expect(await screen.findByRole('button', { name: 'Turn camera on' })).toBeInTheDocument()
  expect(screen.getByLabelText('Your camera')).toHaveClass('hidden')
  await userEvent.type(await screen.findByLabelText('Monaco'), 'def allow(u): pass')
  await userEvent.selectOptions(screen.getByRole('combobox'), 'go')
  // Code alone is enough to send.
  await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))
  expect(sent[0]).toMatchObject({
    text: '(My answer is in the code editor.)',
    work: { kind: 'code', language: 'go', content: 'def allow(u): pass' },
  })

  // The next section is system design: a whiteboard instead of the editor.
  await userEvent.click(await screen.findByRole('button', { name: 'Draw' }))
  expect(screen.queryByLabelText('Monaco')).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Your answer'), 'Redis holds the counters.')
  await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))
  expect(sent[1]).toMatchObject({
    text: 'Redis holds the counters.',
    work: { kind: 'whiteboard', content: 'Components: API, Redis\nConnections: API → Redis' },
  })
  expect(sent.every((b) => !('body' in b))).toBe(true)
})
