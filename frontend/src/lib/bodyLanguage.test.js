import { expect, it } from 'vitest'
import { frameMetrics, summarize } from './bodyLanguage'

// A face looking straight at the camera: eyes level, nose centred, irises centred.
function face({ nose = 0.5, iris = 0.5 } = {}) {
  const pts = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }))
  pts[33] = { x: 0.4, y: 0.4 } // right eye outer
  pts[133] = { x: 0.46, y: 0.4 } // right eye inner
  pts[362] = { x: 0.54, y: 0.4 } // left eye inner
  pts[263] = { x: 0.6, y: 0.4 } // left eye outer
  pts[468] = { x: 0.4 + 0.06 * iris, y: 0.4 }
  pts[473] = { x: 0.54 + 0.06 * iris, y: 0.4 }
  pts[1] = { x: nose, y: 0.5 }
  return pts
}

function pose({ tilt = 0, noseY = 0.3, wrist = 0.8 } = {}) {
  const pts = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, visibility: 0.1 }))
  pts[0] = { x: 0.5, y: noseY, visibility: 0.99 }
  pts[11] = { x: 0.65, y: 0.6, visibility: 0.99 }
  pts[12] = { x: 0.35, y: 0.6 + tilt, visibility: 0.99 }
  pts[15] = { x: wrist, y: 0.9, visibility: 0.9 }
  return pts
}

it('reads eye contact and posture from one frame', () => {
  expect(frameMetrics(face(), pose())).toMatchObject({ face: true, eyeContact: true, upright: true })
  expect(frameMetrics(face({ nose: 0.6 }), pose()).eyeContact).toBe(false) // head turned
  expect(frameMetrics(face({ iris: 0.95 }), pose()).eyeContact).toBe(false) // looking aside
  expect(frameMetrics(face(), pose({ tilt: 0.1 })).upright).toBe(false) // leaning
  expect(frameMetrics(face(), pose({ noseY: 0.55 })).upright).toBe(false) // slouched
  expect(frameMetrics(null, null)).toEqual({ face: false, eyeContact: null, upright: null, points: null })
})

it('summarizes an answer as percentages only', () => {
  const still = frameMetrics(face(), pose())
  const away = frameMetrics(face({ nose: 0.62 }), pose({ wrist: 0.2 }))
  const out = summarize([still, still, away, still])
  expect(out).toEqual({ samples: 4, face_pct: 100, eye_contact_pct: 75, upright_pct: 100, fidget_pct: 67 })
  expect(summarize([])).toBeNull()
})
