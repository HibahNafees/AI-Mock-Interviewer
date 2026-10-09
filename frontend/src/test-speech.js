import { vi } from 'vitest'

// A stand-in for the browser's speechSynthesis; returns the utterances spoken.
export const ALEX = { name: 'Alex', lang: 'en-US', default: true }
export const SAM = { name: 'Sam', lang: 'en-GB' }

export function fakeSpeech(voices = [ALEX, SAM]) {
  const spoken = []
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    constructor(text) {
      this.text = text
    }
  })
  vi.stubGlobal('speechSynthesis', {
    getVoices: () => voices,
    speak: vi.fn((u) => spoken.push(u)),
    cancel: vi.fn(),
  })
  return spoken
}
