import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Recorder from './Recorder'

class FakeMediaRecorder {
  static isTypeSupported = (t) => t === 'audio/webm;codecs=opus'
  constructor(stream, opts) {
    this.stream = stream
    this.mimeType = opts.mimeType
    this.opts = opts
    this.state = 'inactive'
    FakeMediaRecorder.last = this
  }
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    this.ondataavailable({ data: new Blob(['abc'], { type: this.mimeType }) })
    this.onstop()
  }
}

let level = 0
class FakeAudioContext {
  createAnalyser() {
    return {
      fftSize: 0,
      getFloatTimeDomainData: (buf) => buf.fill(level),
    }
  }
  createMediaStreamSource() {
    return { connect() {} }
  }
  close() {}
}

const track = { stop: vi.fn() }

beforeEach(() => {
  level = 0
  track.stop.mockClear()
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal('AudioContext', FakeAudioContext)
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('Recorder', () => {
  it('records until Done and hands over the clip', async () => {
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    expect(FakeMediaRecorder.last.opts.audioBitsPerSecond).toBe(32000)
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))

    expect(onRecorded).toHaveBeenCalledTimes(1)
    const [blob, duration] = onRecorded.mock.calls[0]
    expect(blob.type).toBe('audio/webm;codecs=opus')
    expect(duration).toBeGreaterThanOrEqual(0)
    expect(track.stop).toHaveBeenCalled() // microphone released
  })

  it('cancel discards the clip', async () => {
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onRecorded).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })

  it('stops by itself after speech then silence', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    await act(async () => vi.advanceTimersByTime(700)) // calibrate on silence
    level = 0.3
    await act(async () => vi.advanceTimersByTime(1000)) // speaking
    level = 0
    await act(async () => vi.advanceTimersByTime(2000))
    expect(screen.getByRole('status')).toHaveTextContent('Stopping in')
    await act(async () => vi.advanceTimersByTime(2500))
    expect(onRecorded).toHaveBeenCalledTimes(1)
  })

  it('explains a blocked microphone', async () => {
    navigator.mediaDevices.getUserMedia = vi.fn(async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    })
    render(<Recorder onRecorded={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Microphone access was blocked')
  })
})
