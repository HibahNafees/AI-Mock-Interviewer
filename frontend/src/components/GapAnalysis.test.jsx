import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import GapAnalysis from './GapAnalysis'

afterEach(() => vi.unstubAllGlobals())

it('compares the résumé with the job on request', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        gaps: {
          summary: 'Good fit; no payments experience.',
          counts: { covered: 1, partial: 0, missing: 1 },
          requirements: [
            { requirement: 'Payments domain', status: 'missing', evidence: null, likely_question: 'How would you learn payments?' },
            { requirement: 'API design', status: 'covered', evidence: 'Built the Acme billing API', likely_question: null },
          ],
        },
      }),
    })),
  )
  render(<GapAnalysis resumeId={1} jdId={2} />)
  await userEvent.click(screen.getByRole('button', { name: 'Check my résumé against this job' }))
  expect(await screen.findByText('Good fit; no payments experience.')).toBeInTheDocument()
  expect(screen.getByLabelText('Not on your résumé')).toBeInTheDocument()
  expect(screen.getByText('How would you learn payments?')).toBeInTheDocument()
  expect(screen.getByText('Built the Acme billing API')).toBeInTheDocument()
  const [, opts] = fetch.mock.calls[0]
  expect(JSON.parse(opts.body)).toEqual({ resume_id: 1 })
})
