import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { AuthProvider } from './lib/auth'

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function mockFetch(handler) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts) => {
      const [status, body] = handler(url, opts)
      return { ok: status < 400, status, json: async () => body }
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }

describe('auth flow', () => {
  it('redirects logged-out users to the login page', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  it('logs in, stores the token, and shows the dashboard', async () => {
    mockFetch(() => [200, { access_token: 'tok', user: ADA }])
    renderAt('/login')
    await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'correct-horse')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Welcome, Ada')).toBeInTheDocument()
    expect(localStorage.getItem('mi_token')).toBe('tok')
    expect(fetch).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST' }))
  })

  it('shows the server error on bad credentials', async () => {
    mockFetch(() => [401, { error: 'Incorrect email or password' }])
    renderAt('/login')
    await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-pass')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
  })

  it('restores the session from a stored token', async () => {
    localStorage.setItem('mi_token', 'tok')
    mockFetch((url, opts) => {
      expect(opts.headers.Authorization).toBe('Bearer tok')
      return [200, { user: ADA }]
    })
    renderAt('/')
    expect(await screen.findByText('Welcome, Ada')).toBeInTheDocument()
  })

  it('drops an expired token and returns to login', async () => {
    localStorage.setItem('mi_token', 'old')
    mockFetch(() => [401, { error: 'Your session expired; please log in again' }])
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(localStorage.getItem('mi_token')).toBeNull()
  })
})
