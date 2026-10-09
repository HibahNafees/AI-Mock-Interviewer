export const MAX_ANSWER_MS = 5 * 60 * 1000

export function canRecord() {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  )
}
