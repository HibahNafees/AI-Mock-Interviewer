import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import CompanyResearch from './CompanyResearch'

afterEach(() => vi.unstubAllGlobals())

const RESEARCH = {
  id: 7,
  company: 'Acme Pay',
  summary: 'Billing software for small shops.',
  talking_points: ['Open API for partners'],
  why_us_questions: ['What draws you to billing tools?'],
}

function Harness() {
  const [research, setResearch] = useState(null)
  const [include, setInclude] = useState(false)
  return (
    <>
      <CompanyResearch role="Backend Engineer" research={research} onChange={setResearch} include={include} onIncludeChange={setInclude} />
      <output>{include ? 'included' : 'left out'}</output>
    </>
  )
}

it('reads the site and offers a "Why this company" section', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ research: RESEARCH }) })),
  )
  render(<Harness />)
  expect(screen.getByRole('button', { name: 'Research' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('Company website'), 'acme.example{Enter}')
  expect(await screen.findByText('Acme Pay')).toBeInTheDocument()
  expect(screen.getByText('Open API for partners')).toBeInTheDocument()
  expect(screen.getByText('What draws you to billing tools?')).toBeInTheDocument()
  const [url, opts] = fetch.mock.calls[0]
  expect(url).toBe('/api/company/research')
  expect(JSON.parse(opts.body)).toEqual({ url: 'acme.example', role: 'Backend Engineer' })
  expect(screen.getByText('included')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('checkbox'))
  expect(screen.getByText('left out')).toBeInTheDocument()
})

it('shows why a site could not be read', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: false, status: 400, json: async () => ({ error: "That address isn't a public website" }) })),
  )
  render(<Harness />)
  await userEvent.type(screen.getByLabelText('Company website'), 'http://10.0.0.1')
  await userEvent.click(screen.getByRole('button', { name: 'Research' }))
  expect(await screen.findByRole('alert')).toHaveTextContent("That address isn't a public website")
})
