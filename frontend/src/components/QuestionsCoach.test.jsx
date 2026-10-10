import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import QuestionsCoach from './QuestionsCoach'

afterEach(() => vi.unstubAllGlobals())

it('suggests questions to ask for the job', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        coach: {
          questions: [{ question: 'What would success look like in 90 days?', why: 'shows you plan', topic: 'role' }],
          avoid: ['Leading with salary in a first round.'],
        },
      }),
    })),
  )
  render(<QuestionsCoach jdId={2} />)
  await userEvent.click(screen.getByRole('button', { name: 'Suggest questions' }))
  expect(await screen.findByText('What would success look like in 90 days?')).toBeInTheDocument()
  expect(screen.getByText('The role')).toBeInTheDocument()
  expect(screen.getByText(/Leading with salary/)).toBeInTheDocument()
})
