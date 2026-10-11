import { describe, expect, it } from 'vitest'
import { EARLY_SILENCE_MS, SETTLED_SPEECH_MS, SILENCE_MS, SilenceDetector, rms } from './silence'

function feed(detector, levels, start = 0, step = 100) {
  return levels.map((lvl, i) => detector.update(lvl, start + i * step))
}

describe('rms', () => {
  it('measures loudness', () => {
    expect(rms(new Float32Array([0, 0, 0]))).toBe(0)
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5)
  })
})

describe('SilenceDetector', () => {
  it('never stops before the candidate speaks', () => {
    const d = new SilenceDetector()
    const out = feed(d, Array(200).fill(0.001)) // 20 s of quiet
    expect(out.every((v) => v === null)).toBe(true)
  })

  // Calibrate, then speak for `ms`; returns when the speech ended.
  function speak(d, ms) {
    feed(d, Array(5).fill(0.002)) // calibrate on room noise
    feed(d, Array(ms / 100 + 1).fill(0.2), 500)
    return 500 + ms
  }

  it('counts down after a settled answer and stops after the silence window', () => {
    const d = new SilenceDetector()
    const end = speak(d, SETTLED_SPEECH_MS)
    expect(d.update(0.002, end + 1000)).toBe(SILENCE_MS - 1000)
    expect(d.update(0.002, end + SILENCE_MS)).toBe(0)
  })

  it('waits longer when the answer has barely started (T-88)', () => {
    const d = new SilenceDetector()
    const end = speak(d, 1000)
    expect(d.update(0.002, end + SILENCE_MS)).toBe(EARLY_SILENCE_MS - SILENCE_MS)
    expect(d.update(0.002, end + EARLY_SILENCE_MS)).toBe(0)
  })

  it('speaking again resets the countdown', () => {
    const d = new SilenceDetector()
    const end = speak(d, SETTLED_SPEECH_MS)
    d.update(0.002, end + 2000)
    expect(d.update(0.3, end + 2500)).toBeNull()
    expect(d.update(0.002, end + 3500)).toBe(SILENCE_MS - 1000)
  })

  it('raises the threshold in a noisy room', () => {
    const d = new SilenceDetector()
    feed(d, Array(5).fill(0.05)) // noisy floor → threshold 0.15
    expect(d.threshold).toBeCloseTo(0.15)
    d.update(0.08, 600) // background noise, not speech
    expect(d.heardSpeech).toBe(false)
  })
})
