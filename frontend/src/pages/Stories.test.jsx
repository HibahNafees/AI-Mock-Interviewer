import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada Lovelace', email: 'ada@example.com' }
const STORY = {
  id: 5,
  title: 'Cut API latency with a nightly ETL',
  star: { situation: 'Reporting queries were slowing our API', task: null, action: 'I moved them to a nightly ETL job', result: null },
  missing: ['task', 'result'],
  competencies: ['SQL Proficiency', 'Problem solving'],
  strength: 3.6,
  user_edited: false,
  sources: [{ session_id: 7, role: 'Backend Engineer', question: 'Tell me about Acme.', date: '2026-10-09' }],
}
const COVERAGE = {
  job: 'Backend Engineer',
  rows: [
    { competency: 'SQL Proficiency', core: false, stories: [5] },
    { competency: 'Problem solving', core: true, stories: [5] },
    { competency: 'Conflict', core: true, stories: [] },
    { competency: 'Failure and learning', core: true, stories: [] },
  ],
  gaps: ['Conflict', 'Failure and learning'],
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

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('story bank', () => {
  it('shows stories with STAR gaps flagged and the coverage gaps', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/stories': [200, { stories: [STORY], coverage: COVERAGE }],
    })
    renderAt('/stories')
    expect(await screen.findByText('Cut API latency with a nightly ETL')).toBeInTheDocument()
    expect(screen.getByText('I moved them to a nightly ETL job')).toBeInTheDocument()
    expect(screen.getAllByText('Not said yet. Add it so the story lands.')).toHaveLength(2)
    expect(screen.getByLabelText('Strength 3.6 out of 5')).toBeInTheDocument()
    expect(screen.getByText(/no story yet for conflict, failure and learning/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Backend Engineer/ })).toHaveAttribute('href', '/report/7')
  })

  it('edits a story', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/stories': [200, { stories: [STORY], coverage: COVERAGE }],
      'PUT /api/stories/5': (opts) => {
        const body = JSON.parse(opts.body)
        return [200, { story: { ...STORY, title: body.title, star: { ...STORY.star, result: body.result }, missing: ['task'], user_edited: true } }]
      },
    })
    renderAt('/stories')
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const title = screen.getByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'My ETL story')
    await userEvent.type(screen.getByLabelText(/^Result/), 'Latency fell to 300 ms.')
    await userEvent.click(screen.getByRole('button', { name: 'Save story' }))
    expect(await screen.findByText('My ETL story')).toBeInTheDocument()
    expect(screen.getByText('Latency fell to 300 ms.')).toBeInTheDocument()
    const sent = JSON.parse(calls.find((c) => c.key === 'PUT /api/stories/5').opts.body)
    expect(sent.competencies).toEqual(['SQL Proficiency', 'Problem solving'])
  })

  it('deletes a story after confirming', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/stories': [200, { stories: [STORY], coverage: COVERAGE }],
      'DELETE /api/stories/5': [200, { ok: true }],
    })
    renderAt('/stories')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
  })

  it('explains the empty bank', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/stories': [200, { stories: [], coverage: { ...COVERAGE, rows: [] } }],
    })
    renderAt('/stories')
    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start a mock interview' })).toBeInTheDocument()
  })
})

describe('dashboard progress', () => {
  const STATS = {
    interviews: 2,
    started: 2,
    practice_minutes: 12,
    questions_answered: 6,
    retries: 1,
    average_score: 3.4,
    best_score: 3.8,
    latest_score: 3.8,
    improvement: 0.8,
    history: [],
    roles: [{ role: 'Backend Engineer', interviews: 2, average_score: 3.4 }],
    skills: [{ name: 'Structure', score: 3.5, count: 4, change: 1.0 }],
    streak_days: 2,
    level: 2,
    next_level_in: 2,
    goal: { weekly: 3, done_this_week: 2 },
    practice: { due: 2, upcoming: 1, mastered: 0 },
  }

  it('starts a weak-spot interview from the practice queue', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions': [200, { sessions: [] }],
      'GET /api/stats': [200, { stats: STATS }],
      'POST /api/sessions/practice': [201, { session: { id: 42 } }],
      'GET /api/sessions/42': [200, { session: { id: 42, status: 'planned', plan: { sections: [], reserve: [] }, transcript: [], analysis: {} } }],
    })
    renderAt('/')
    const card = (await screen.findByRole('heading', { name: 'Practice queue' })).closest('div.card')
    expect(within(card).getByText('2')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Practice my weak spots' }))
    expect(await screen.findByText('Your interview plan')).toBeInTheDocument()
  })

  it('shows and changes the weekly goal, and skill change', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions': [200, { sessions: [] }],
      'GET /api/stats': [200, { stats: STATS }],
      'PUT /api/stats/goal': (opts) => [200, { stats: { ...STATS, goal: { ...STATS.goal, weekly: JSON.parse(opts.body).weekly_goal } } }],
    })
    renderAt('/')
    expect(await screen.findByText('1 more to reach your goal.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Raise weekly goal' }))
    expect(await screen.findByText('2 more to reach your goal.')).toBeInTheDocument()
    expect(screen.getByText('▲ +1.0')).toBeInTheDocument()
  })
})

describe('setup suggestions', () => {
  it('suggests stories that fit the chosen job', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [{ id: 1, title: 'CV' }] }],
      'GET /api/documents?kind=job_description': [200, { documents: [{ id: 2, title: 'Job' }] }],
      'POST /api/documents/2/analysis': [200, { analysis: { role_title: 'Backend Engineer', field: 'software', competencies: [] }, modules: [] }],
      'GET /api/stories/suggest?jd_id=2': [200, { stories: [{ id: 5, title: 'Cut API latency with a nightly ETL', fits: ['Databases'], strength: 3.6 }] }],
    })
    renderAt('/setup')
    expect(await screen.findByText('Stories that fit this job')).toBeInTheDocument()
    expect(screen.getByText('Cut API latency with a nightly ETL')).toBeInTheDocument()
    expect(screen.getByText('Databases')).toBeInTheDocument()
  })
})
