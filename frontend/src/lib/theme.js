import { useEffect, useState } from 'react'

const THEME_KEY = 'mi_theme'
const listeners = new Set()

// 'light' (the default) or 'dark', remembered per browser.
export function themePref() {
  try {
    if (localStorage.getItem(THEME_KEY) === 'dark') return 'dark'
  } catch {
    // Storage unavailable: light.
  }
  return 'light'
}

// Sets <html data-theme>, which index.css keys the dark palette on. index.html
// runs the same logic inline before the app loads, so pages never flash.
export function applyTheme(theme = themePref()) {
  document.documentElement.dataset.theme = theme
  listeners.forEach((fn) => fn(theme))
  return theme
}

export function setThemePref(theme) {
  try {
    if (theme === 'dark') localStorage.setItem(THEME_KEY, 'dark')
    else localStorage.removeItem(THEME_KEY)
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
  applyTheme(theme)
}

// The theme in effect right now ('light' | 'dark'), for widgets that take a
// theme prop (code editor, whiteboard).
export function useTheme() {
  const [theme, setTheme] = useState(themePref)
  useEffect(() => {
    listeners.add(setTheme)
    return () => listeners.delete(setTheme)
  }, [])
  return theme
}
