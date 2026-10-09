import { useEffect, useRef, useState } from 'react'
import { MAX_ANSWER_MS } from '../lib/recording'
import { SilenceDetector, rms } from '../lib/silence'

const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4']
const COUNTDOWN_FROM_MS = 2500 // show "stopping in…" for the last part of the silence

function pickMimeType() {
  const MR = window.MediaRecorder
  return MIME_TYPES.find((t) => MR.isTypeSupported?.(t)) ?? ''
}

function clock(ms) {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Records one answer. Stops on "Done", after a few seconds of silence, or at 5 minutes,
// then calls onRecorded(blob, durationMs). The clip lives only in memory.
export default function Recorder({ onRecorded, onStart, disabled }) {
  const [state, setState] = useState('idle') // idle | starting | recording
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [level, setLevel] = useState(0)
  const [stopIn, setStopIn] = useState(null)
  const rec = useRef(null)

  function cleanup() {
    const r = rec.current
    if (!r) return
    clearInterval(r.interval)
    r.stream.getTracks().forEach((t) => t.stop())
    r.audio?.close?.()
    rec.current = null
  }

  useEffect(() => cleanup, [])

  function finish(keep) {
    const r = rec.current
    if (!r || r.finishing) return
    r.finishing = true
    r.keep = keep
    clearInterval(r.interval)
    r.duration = Date.now() - r.startedAt
    if (r.recorder.state !== 'inactive') r.recorder.stop()
    else r.recorder.onstop()
  }

  async function start() {
    setError('')
    setState('starting')
    onStart?.()
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch (err) {
      setState('idle')
      setError(
        err?.name === 'NotAllowedError'
          ? 'Microphone access was blocked. Allow it in your browser, or type your answer.'
          : 'No microphone found. You can type your answer instead.',
      )
      return
    }

    const mimeType = pickMimeType()
    const recorder = new window.MediaRecorder(stream, {
      ...(mimeType ? { mimeType } : {}),
      audioBitsPerSecond: 32000,
    })
    const chunks = []
    const r = { stream, recorder, startedAt: Date.now(), finishing: false }
    rec.current = r

    recorder.ondataavailable = (e) => {
      if (e.data?.size) chunks.push(e.data)
    }
    recorder.onstop = () => {
      const { keep, duration } = r
      const type = recorder.mimeType || mimeType || 'audio/webm'
      cleanup()
      setState('idle')
      setStopIn(null)
      setLevel(0)
      if (keep) onRecorded(new Blob(chunks, { type }), duration)
    }

    // Loudness meter + silence auto-stop.
    const detector = new SilenceDetector()
    let read = () => 0
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext
      const audio = new AudioCtx()
      const analyser = audio.createAnalyser()
      analyser.fftSize = 2048
      audio.createMediaStreamSource(stream).connect(analyser)
      const buf = new Float32Array(analyser.fftSize)
      r.audio = audio
      read = () => {
        analyser.getFloatTimeDomainData(buf)
        return rms(buf)
      }
    } catch {
      // No Web Audio: still record, just without the meter and auto-stop.
    }

    r.interval = setInterval(() => {
      const now = Date.now()
      const ms = now - r.startedAt
      const lvl = read()
      const left = detector.update(lvl, now)
      setElapsed(ms)
      setLevel(lvl)
      setStopIn(left !== null && left <= COUNTDOWN_FROM_MS ? left : null)
      if (left === 0 || ms >= MAX_ANSWER_MS) finish(true)
    }, 100)

    recorder.start(1000)
    setElapsed(0)
    setState('recording')
  }

  if (state !== 'recording') {
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={start}
          disabled={disabled || state === 'starting'}
          className="btn-primary px-6 py-3 text-base"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
          </svg>
          {state === 'starting' ? 'Starting microphone…' : 'Record answer'}
        </button>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => finish(true)}
          className="relative inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-rose-500 to-red-500 px-6 py-3 font-semibold text-white shadow-md shadow-rose-500/30 transition hover:from-rose-600 hover:to-red-600"
        >
          <span aria-hidden="true" className="absolute inset-0 animate-ping rounded-full bg-rose-400/30" />
          <span aria-hidden="true" className="h-3 w-3 rounded-sm bg-white" />
          Done
        </button>
        <button
          type="button"
          onClick={() => finish(false)}
          className="btn-link"
        >
          Cancel
        </button>
        <span aria-label="Recording time" className="rounded-full bg-slate-100 px-3 py-1 font-mono text-sm tabular-nums text-slate-700">
          {clock(elapsed)} / {clock(MAX_ANSWER_MS)}
        </span>
        <span
          aria-hidden="true"
          className="h-2.5 w-28 overflow-hidden rounded-full bg-slate-200"
          title="Microphone level"
        >
          <span
            className="block h-full rounded-full bg-gradient-to-r from-teal-400 to-emerald-500 transition-[width] duration-100"
            style={{ width: `${Math.min(100, level * 400)}%` }}
          />
        </span>
      </div>
      <p role="status" className="text-sm text-slate-500">
        {stopIn !== null
          ? `Stopping in ${Math.ceil(stopIn / 1000)}… keep talking to continue.`
          : 'Recording… tap Done when you finish, or pause for a few seconds.'}
      </p>
    </div>
  )
}
