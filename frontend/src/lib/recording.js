export const MAX_ANSWER_MS = 5 * 60 * 1000

export function canRecord() {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  )
}

const MODE_KEY = 'mi_answer_mode'

// How the user likes to answer: 'voice' (record) or 'text' (type). Remembered
// between interviews; falls back to typing where recording isn't possible.
export function answerModePref() {
  let saved = null
  try {
    saved = localStorage.getItem(MODE_KEY)
  } catch {
    // Storage unavailable: use the default.
  }
  if (!canRecord()) return 'text'
  return saved === 'text' ? 'text' : 'voice'
}

export function setAnswerModePref(mode) {
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
}
