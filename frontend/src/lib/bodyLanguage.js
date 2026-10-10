// Body language feedback (opt-in): MediaPipe face and pose landmarks, computed in
// the browser. Video never leaves the device; only a few percentages per answer
// are sent with it.

const VERSION = '1.1.0'
const WASM = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/wasm`
const FACE_MODEL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
const POSE_MODEL =
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'

// Face mesh indices: eye corners, iris centres, nose tip.
const R_OUT = 33
const R_IN = 133
const L_IN = 362
const L_OUT = 263
const R_IRIS = 468
const L_IRIS = 473
const NOSE = 1
// Pose indices.
const P_NOSE = 0
const L_SHOULDER = 11
const R_SHOULDER = 12
const L_WRIST = 15
const R_WRIST = 16

// Thresholds are deliberately forgiving: this is a practice hint, not a judgment.
const MAX_HEAD_TURN = 0.18 // nose offset from the eye midpoint, in eye widths
const IRIS_CENTRE = [0.3, 0.7] // iris position between the eye corners
const MAX_SHOULDER_TILT = 0.12 // shoulder height difference, in shoulder widths
const MIN_HEAD_RISE = 0.35 // nose above the shoulder line, in shoulder widths
const FIDGET_MOTION = 0.08 // movement between samples, in shoulder widths

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)
const seen = (p) => p && (p.visibility === undefined || p.visibility > 0.5)

function ratio(p, a, b) {
  const len = dist(a, b) || 1
  return ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / (len * len)
}

// One frame → { face, eyeContact, upright, points } (null where not visible).
export function frameMetrics(face, pose) {
  const out = { face: Boolean(face), eyeContact: null, upright: null, points: null }
  if (face) {
    const eyeMid = { x: (face[R_OUT].x + face[L_OUT].x) / 2, y: (face[R_OUT].y + face[L_OUT].y) / 2 }
    const eyeWidth = dist(face[R_OUT], face[L_OUT]) || 1
    const facing = Math.abs(face[NOSE].x - eyeMid.x) / eyeWidth < MAX_HEAD_TURN
    let gaze = true
    if (face[R_IRIS] && face[L_IRIS]) {
      const r = ratio(face[R_IRIS], face[R_OUT], face[R_IN])
      const l = ratio(face[L_IRIS], face[L_IN], face[L_OUT])
      const [lo, hi] = IRIS_CENTRE
      gaze = r > lo && r < hi && l > lo && l < hi
    }
    out.eyeContact = facing && gaze
  }
  if (pose && seen(pose[L_SHOULDER]) && seen(pose[R_SHOULDER])) {
    const width = dist(pose[L_SHOULDER], pose[R_SHOULDER]) || 1
    const tilt = Math.abs(pose[L_SHOULDER].y - pose[R_SHOULDER].y) / width
    const shoulderY = (pose[L_SHOULDER].y + pose[R_SHOULDER].y) / 2
    const rise = seen(pose[P_NOSE]) ? (shoulderY - pose[P_NOSE].y) / width : MIN_HEAD_RISE
    out.upright = tilt < MAX_SHOULDER_TILT && rise >= MIN_HEAD_RISE
    out.points = { width, at: [P_NOSE, L_WRIST, R_WRIST].filter((i) => seen(pose[i])).map((i) => ({ i, ...pose[i] })) }
  }
  return out
}

function moved(prev, next) {
  if (!prev?.points || !next?.points) return null
  const before = new Map(prev.points.at.map((p) => [p.i, p]))
  const shifts = next.points.at.filter((p) => before.has(p.i)).map((p) => dist(p, before.get(p.i)))
  if (!shifts.length) return null
  return Math.max(...shifts) / next.points.width > FIDGET_MOTION
}

const pct = (flags) => {
  const known = flags.filter((f) => f !== null)
  return known.length ? Math.round((100 * known.filter(Boolean).length) / known.length) : null
}

// Frames of one answer → what's sent: percentages only, no images or landmarks.
export function summarize(frames) {
  if (!frames.length) return null
  const motion = frames.slice(1).map((f, i) => moved(frames[i], f))
  return {
    samples: frames.length,
    face_pct: pct(frames.map((f) => f.face)),
    eye_contact_pct: pct(frames.map((f) => f.eyeContact)),
    upright_pct: pct(frames.map((f) => f.upright)),
    fidget_pct: pct(motion),
  }
}

export function canUseCamera() {
  return typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)
}

// Loads both models (a few MB, cached by the browser after the first time).
export async function createTracker() {
  const { FilesetResolver, FaceLandmarker, PoseLandmarker } = await import('@mediapipe/tasks-vision')
  const vision = await FilesetResolver.forVisionTasks(WASM)
  const [face, pose] = await Promise.all([
    FaceLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: FACE_MODEL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numFaces: 1,
    }),
    PoseLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: POSE_MODEL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numPoses: 1,
    }),
  ])
  return {
    detect(video, now) {
      const f = face.detectForVideo(video, now).faceLandmarks?.[0] ?? null
      const p = pose.detectForVideo(video, now).landmarks?.[0] ?? null
      return frameMetrics(f, p)
    },
    close() {
      face.close()
      pose.close()
    },
  }
}
