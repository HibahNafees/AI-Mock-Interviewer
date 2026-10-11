// Decides when an answer is over: after the candidate has spoken, a few seconds of
// quiet stops the recording. It never stops before any speech (they may be thinking),
// and early in an answer it waits longer: "So, when I worked..." and a pause to
// think is not the end of an answer (T-88).

export const SILENCE_MS = 4000
export const EARLY_SILENCE_MS = 8000
// Speech needed before the normal pause length applies.
export const SETTLED_SPEECH_MS = 5000
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
    this.speechMs = 0
    this.last = null
  }

  get threshold() {
    // The quietest level in the first half-second is the room's noise floor.
    return Math.max(MIN_THRESHOLD, Number.isFinite(this.noise) ? this.noise * 3 : 0)
  }

  // Feed one loudness reading; returns ms of silence left before auto-stop, or
  // null while no countdown applies (no speech yet, or currently speaking).
  update(level, now) {
    if (this.start === null) this.start = now
    const step = this.last === null ? 0 : now - this.last
    this.last = now
    if (now - this.start < CALIBRATE_MS) {
      this.noise = Math.min(this.noise, level)
      return null
    }
    if (level >= this.threshold) {
      this.heardSpeech = true
      this.lastLoud = now
      this.speechMs += step
      return null
    }
    if (!this.heardSpeech) return null
    const wait = this.speechMs < SETTLED_SPEECH_MS ? Math.max(this.silenceMs, EARLY_SILENCE_MS) : this.silenceMs
    return Math.max(0, wait - (now - this.lastLoud))
  }
}
