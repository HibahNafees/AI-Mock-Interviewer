import { useState } from 'react'
import { setThemePref, themePref } from '../lib/theme'

// One click switches between light and dark. The icon shows where a click
// takes you: a moon in light mode, a sun in dark mode.
export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(themePref)
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = `Switch to ${next} mode`
  return (
    <button
      type="button"
      onClick={() => {
        setThemePref(next)
        setTheme(next)
      }}
      className={`grid h-9 w-9 place-items-center rounded-full text-base ring-1 ring-line transition hover:bg-surface ${className}`}
      aria-label={label}
      title={label}
    >
      <span aria-hidden="true">{next === 'dark' ? '🌙' : '☀️'}</span>
    </button>
  )
}
