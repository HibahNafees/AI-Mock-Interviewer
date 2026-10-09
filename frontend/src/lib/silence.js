// Decides when an answer is over: after the candidate has spoken, a few seconds of
// quiet stops the recording. It never stops before any speech (they may be thinking).

export const SILENCE_MS = 4000
const CALIBRATE_MS = 500
const MIN_THRESHOLD = 0.01

// Root-mean-square loudness of a block of samples in [-1, 1].
export function rms(samples) {
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / (samples.length || 1))
}

export class SilenceDetector {
  constructor({ silenceMs = SILENCE_MS } = {}) {
    this.silenceMs = silenceMs
    this.start = null
    this.noise = Infinity
    this.heardSpeech = false
    this.lastLoud = 0
  }

  get threshold() {
    // The quietest level in the first half-second is the room's noise floor.
    return Math.max(MIN_THRESHOLD, Number.isFinite(this.noise) ? this.noise * 3 : 0)
  }

  // Feed one loudness reading; returns ms of silence left before auto-stop, or
  // null while no countdown applies (no speech yet, or currently speaking).
  update(level, now) {
    if (this.start === null) this.start = now
    if (now - this.start < CALIBRATE_MS) {
      this.noise = Math.min(this.noise, level)
      return null
    }
    if (level >= this.threshold) {
      this.heardSpeech = true
      this.lastLoud = now
      return null
    }
    if (!this.heardSpeech) return null
    return Math.max(0, this.silenceMs - (now - this.lastLoud))
  }
}
