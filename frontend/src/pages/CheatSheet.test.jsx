import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }

afterEach(() => vi.unstubAllGlobals())

it('shows a printable cheat sheet', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      if (url.endsWith('/auth/me')) return { ok: true, status: 200, json: async () => ({ user: ADA }) }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          sheet: {
            role_title: 'Backend Engineer',
            company: null,
            stories: [{ title: 'Cut API latency', action: 'Moved reports to a nightly ETL', result: 'p95 300 ms', fits: ['SQL'] }],
            key_numbers: ['p95 latency dropped from 1.8 seconds to 300 milliseconds.'],
            weak_spots: [{ name: 'Structure', score: 2.8 }],
            takeaways: ['Lead with the point.'],
            likely_questions: ['How would you learn payments?'],
            questions_to_ask: ['What does success look like in 90 days?'],
          },
        }),
      }
    }),
  )
  window.print = vi.fn()
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={['/report/7/cheatsheet']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText('Cut API latency')).toBeInTheDocument()
  expect(screen.getByText('p95 latency dropped from 1.8 seconds to 300 milliseconds.')).toBeInTheDocument()
  expect(screen.getByText('What does success look like in 90 days?')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Save as PDF / print' }))
  expect(window.print).toHaveBeenCalled()
})
