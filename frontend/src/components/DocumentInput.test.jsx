import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DialogProvider } from './ConfirmDialog'
import DocumentInput from './DocumentInput'

// DocumentInput asks before deleting through the app's dialog provider.
const render = (ui) => {
  const out = rtlRender(<DialogProvider>{ui}</DialogProvider>)
  return { ...out, rerender: (next) => out.rerender(<DialogProvider>{next}</DialogProvider>) }
}

function respond() {
  const sent = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      if (opts.method === 'POST') {
        sent.push(opts.body)
        return { ok: true, status: 201, json: async () => ({ document: { id: 5, title: 'cv.pdf' } }) }
      }
      return { ok: true, status: 200, json: async () => ({ documents: [] }) }
    }),
  )
  return sent
}

afterEach(() => vi.unstubAllGlobals())

describe('document upload', () => {
  // T-30: the bare file input showed no button, so users couldn't see where to click.
  it('shows a visible Choose file button that opens the picker', async () => {
    const sent = respond()
    const onChange = vi.fn()
    render(<DocumentInput kind="resume" value={null} onChange={onChange} />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Upload file' }))
    expect(screen.getByText('Choose file')).toBeVisible()

    const file = new File(['My résumé text'], 'cv.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByLabelText('Upload your résumé file'), file)
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(5))
    expect(sent[0].get('file').name).toBe('cv.pdf')
    expect(sent[0].get('kind')).toBe('resume')
  })

  it('accepts a dropped file', async () => {
    const sent = respond()
    render(<DocumentInput kind="job_description" value={null} onChange={vi.fn()} />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Upload file' }))
    const file = new File(['Job text'], 'job.txt', { type: 'text/plain' })
    fireEvent.drop(screen.getByText('Choose file'), { dataTransfer: { files: [file] } })
    await vi.waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0].get('file').name).toBe('job.txt')
  })
})

describe('saved documents', () => {
  it('deletes the chosen saved job posting and picks the next one', async () => {
    const deleted = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, opts = {}) => {
        if (opts.method === 'DELETE') {
          deleted.push(url)
          return { ok: true, status: 204, json: async () => ({}) }
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            documents: [
              { id: 1, title: 'Acme backend' },
              { id: 2, title: 'Data role' },
            ],
          }),
        }
      }),
    )
    const onChange = vi.fn()
    const { rerender } = render(<DocumentInput kind="job_description" value={null} onChange={onChange} />)
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(1))
    rerender(<DocumentInput kind="job_description" value={1} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Delete this saved job posting' }))
    await userEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(onChange).toHaveBeenLastCalledWith(2))
    expect(deleted).toEqual(['/api/documents/1'])
    expect(screen.queryByRole('option', { name: 'Acme backend' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Job posting deleted')
  })

  it('saves a document so it is kept past 30 days', async () => {
    const posted = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, opts = {}) => {
        if (opts.method === 'POST') {
          posted.push(url)
          return { ok: true, status: 200, json: async () => ({ document: { id: 1, saved: true, expires_at: null } }) }
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            documents: [{ id: 1, title: 'Acme backend', saved: false, expires_at: '2026-11-11T00:00:00Z' }],
          }),
        }
      }),
    )
    render(<DocumentInput kind="job_description" value={1} onChange={vi.fn()} />)
    expect(await screen.findByText(/Auto-deletes on/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save this job posting' }))
    expect(await screen.findByText('Saved: kept until you delete it.')).toBeInTheDocument()
    expect(posted).toEqual(['/api/documents/1/save'])
    expect(screen.queryByRole('button', { name: 'Save this job posting' })).not.toBeInTheDocument()
  })

  it('optional: picks nothing until the user does', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ documents: [{ id: 1, title: 'Acme backend' }] }),
      })),
    )
    const onChange = vi.fn()
    render(<DocumentInput kind="job_description" value={null} onChange={onChange} optional />)
    expect(await screen.findByRole('option', { name: 'None' })).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })
})
