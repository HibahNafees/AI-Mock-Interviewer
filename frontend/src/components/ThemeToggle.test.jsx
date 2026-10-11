import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle'

afterEach(() => localStorage.clear())

it('switches light ↔ dark in one click each', async () => {
  render(<ThemeToggle />)
  await userEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
  expect(document.documentElement.dataset.theme).toBe('dark')
  await userEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }))
  expect(document.documentElement.dataset.theme).toBe('light')
})
