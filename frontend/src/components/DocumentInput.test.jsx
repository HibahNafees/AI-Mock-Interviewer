import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentInput from './DocumentInput'

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
