import { describe, expect, it } from 'vitest'
import { SILENCE_MS, SilenceDetector, rms } from './silence'

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

  it('counts down after speech and stops after the silence window', () => {
    const d = new SilenceDetector()
    feed(d, Array(5).fill(0.002)) // calibrate on room noise
    expect(d.update(0.2, 600)).toBeNull() // speaking
    expect(d.update(0.002, 1600)).toBe(SILENCE_MS - 1000)
    expect(d.update(0.002, 600 + SILENCE_MS)).toBe(0)
  })

  it('speaking again resets the countdown', () => {
    const d = new SilenceDetector()
    feed(d, Array(5).fill(0.002))
    d.update(0.2, 600)
    d.update(0.002, 3000)
    expect(d.update(0.3, 3500)).toBeNull()
    expect(d.update(0.002, 4500)).toBe(SILENCE_MS - 1000)
  })

  it('raises the threshold in a noisy room', () => {
    const d = new SilenceDetector()
    feed(d, Array(5).fill(0.05)) // noisy floor → threshold 0.15
    expect(d.threshold).toBeCloseTo(0.15)
    d.update(0.08, 600) // background noise, not speech
    expect(d.heardSpeech).toBe(false)
  })
})
