import { afterEach, describe, expect, it } from 'vitest'
import { applyTheme, setThemePref, themePref } from './theme'

describe('theme', () => {
  afterEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('is light by default', () => {
    expect(themePref()).toBe('light')
    expect(applyTheme()).toBe('light')
  })

  it('remembers dark and sets data-theme', () => {
    setThemePref('dark')
    expect(themePref()).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    setThemePref('light')
    expect(localStorage.getItem('mi_theme')).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('treats anything else in storage as light', () => {
    localStorage.setItem('mi_theme', 'system')
    expect(themePref()).toBe('light')
  })
})
