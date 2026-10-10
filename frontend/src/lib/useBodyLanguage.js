import { useCallback, useEffect, useRef, useState } from 'react'
import { canUseCamera, createTracker, summarize } from './bodyLanguage'

const SAMPLE_MS = 250 // 4 frames a second is plenty for posture and eye contact
// Detection runs on the main thread: on a slow device, wait longer between
// frames so it never takes more than about a third of the time.
const BUSY_FACTOR = 2

// Camera + MediaPipe for one interview. Off until the candidate turns it on.
// reset() when a question is asked; take() when the answer is sent.
export function useBodyLanguage() {
  const [status, setStatus] = useState('off') // off | loading | on | error
  const [error, setError] = useState('')
  const videoRef = useRef(null)
  const stream = useRef(null)
  const tracker = useRef(null)
  const timer = useRef(null)
  const frames = useRef([])

  const stop = useCallback(() => {
    clearTimeout(timer.current)
    timer.current = null
    stream.current?.getTracks().forEach((t) => t.stop())
    tracker.current?.close()
    stream.current = tracker.current = null
    frames.current = []
  }, [])

  useEffect(() => stop, [stop])

  async function enable() {
    if (!canUseCamera()) {
      setStatus('error')
      setError("This browser can't use a camera here.")
      return
    }
    setError('')
    setStatus('loading')
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
      const video = videoRef.current
      video.srcObject = stream.current
      await video.play()
      tracker.current = await createTracker()
      const sample = () => {
        if (!tracker.current) return
        let took = 0
        if (video.readyState >= 2) {
          const started = performance.now()
          try {
            frames.current.push(tracker.current.detect(video, started))
          } catch {
            // A dropped frame doesn't matter.
          }
          took = performance.now() - started
        }
        timer.current = setTimeout(sample, Math.max(SAMPLE_MS, took * BUSY_FACTOR))
      }
      timer.current = setTimeout(sample, SAMPLE_MS)
      setStatus('on')
    } catch (err) {
      stop()
      setStatus('error')
      setError(
        err?.name === 'NotAllowedError'
          ? 'Camera permission was denied, so body language feedback is off.'
          : "Couldn't start the camera or load the body-language model.",
      )
    }
  }

  function disable() {
    stop()
    setStatus('off')
  }

  const reset = useCallback(() => {
    frames.current = []
  }, [])

  // This answer's summary (percentages only), or null when off.
  const take = useCallback(() => {
    if (status !== 'on') return null
    const out = summarize(frames.current)
    frames.current = []
    return out
  }, [status])

  return { status, error, videoRef, enable, disable, reset, take }
}
