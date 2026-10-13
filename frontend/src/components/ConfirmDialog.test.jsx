import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DialogProvider, useDialogs } from './ConfirmDialog'

// A page with one button that asks, then reports what the dialog returned.
function Asker({ onConfirm, onResult }) {
  const { confirm, notify } = useDialogs()
  async function ask() {
    const ok = await confirm({
      title: 'Delete this interview?',
      message: '“Backend Engineer” and its answers and report will be permanently deleted.',
      confirmLabel: 'Delete',
      busyLabel: 'Deleting…',
      danger: true,
      onConfirm,
    })
    onResult(ok)
    if (ok) notify('Interview deleted')
  }
  return (
    <button type="button" onClick={ask}>
      Ask
    </button>
  )
}

function setup(onConfirm) {
  const onResult = vi.fn()
  render(
    <DialogProvider>
      <Asker onConfirm={onConfirm} onResult={onResult} />
    </DialogProvider>,
  )
  return onResult
}

async function open() {
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
  return screen.findByRole('alertdialog', { name: 'Delete this interview?' })
}

describe('ConfirmDialog (T-137)', () => {
  it('is a labelled modal with Cancel focused first', async () => {
    setup()
    const dialog = await open()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleDescription(/permanently deleted/)
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('Cancel, Esc and a click outside all cancel, and focus goes back', async () => {
    const onResult = setup()
    await open()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onResult).toHaveBeenLastCalledWith(false)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toHaveFocus()

    await open()
    await userEvent.keyboard('{Escape}')
    expect(onResult).toHaveBeenCalledTimes(2)
    expect(onResult).toHaveBeenLastCalledWith(false)

    const dialog = await open()
    fireEvent.mouseDown(dialog) // inside: stays open
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    fireEvent.mouseDown(dialog.parentElement) // the backdrop
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await vi.waitFor(() => expect(onResult).toHaveBeenCalledTimes(3))
    expect(onResult).toHaveBeenLastCalledWith(false)
  })

  it('keeps Tab inside the dialog', async () => {
    setup()
    await open()
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const del = screen.getByRole('button', { name: 'Delete' })
    await userEvent.tab()
    expect(del).toHaveFocus()
    await userEvent.tab()
    expect(cancel).toHaveFocus()
    await userEvent.tab({ shift: true })
    expect(del).toHaveFocus()
  })

  it('shows Deleting… while it works, then a small done message', async () => {
    let finish
    const onConfirm = vi.fn(() => new Promise((resolve) => (finish = resolve)))
    const onResult = setup(onConfirm)
    await open()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await userEvent.keyboard('{Escape}') // can't cancel half-way
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    finish()
    await vi.waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(onResult).toHaveBeenLastCalledWith(true)
    expect(screen.getByRole('status')).toHaveTextContent('Interview deleted')
  })

  it('keeps the dialog open with the error when the action fails', async () => {
    const onConfirm = vi.fn().mockRejectedValueOnce(new Error('Interview not found')).mockResolvedValueOnce()
    const onResult = setup(onConfirm)
    await open()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Interview not found')
    expect(onResult).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(onResult).toHaveBeenLastCalledWith(true))
  })
})
