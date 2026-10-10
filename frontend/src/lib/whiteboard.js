// The whiteboard sketch as text: what the interviewer and the scorer read. Only
// this text is sent; the drawing itself never leaves the browser.

const SHAPES = new Set(['rectangle', 'ellipse', 'diamond'])
const KIND = { rectangle: 'box', ellipse: 'circle', diamond: 'diamond' }

function clean(text) {
  return (text ?? '').replace(/\s+/g, ' ').trim()
}

export function describeScene(elements) {
  const live = (elements ?? []).filter((e) => !e.isDeleted)
  const byId = new Map(live.map((e) => [e.id, e]))
  // Text typed inside a shape or on an arrow is bound to it via containerId.
  const boundText = new Map()
  for (const e of live) {
    if (e.type === 'text' && e.containerId) boundText.set(e.containerId, clean(e.text))
  }
  const shapes = live.filter((e) => SHAPES.has(e.type))
  const counts = {}
  const names = new Map()
  for (const s of shapes) {
    const label = boundText.get(s.id)
    counts[s.type] = (counts[s.type] ?? 0) + 1
    names.set(s.id, label || `unlabeled ${KIND[s.type]} ${counts[s.type]}`)
  }
  const nameOf = (binding) => {
    const target = binding?.elementId && byId.get(binding.elementId)
    if (!target) return 'nothing'
    return names.get(target.id) ?? (target.type === 'text' ? `"${clean(target.text)}"` : target.type)
  }
  const arrows = live
    .filter((e) => e.type === 'arrow')
    .map((a) => {
      const label = boundText.get(a.id)
      return `${nameOf(a.startBinding)} → ${nameOf(a.endBinding)}${label ? ` ("${label}")` : ''}`
    })
  const notes = live.filter((e) => e.type === 'text' && !e.containerId && clean(e.text)).map((e) => `"${clean(e.text)}"`)
  const strokes = live.filter((e) => e.type === 'freedraw' || e.type === 'line').length

  const lines = []
  if (shapes.length) lines.push(`Components: ${shapes.map((s) => names.get(s.id)).join(', ')}`)
  if (arrows.length) lines.push(`Connections: ${arrows.join('; ')}`)
  if (notes.length) lines.push(`Notes: ${notes.join('; ')}`)
  if (strokes) lines.push(`Plus ${strokes} freehand line${strokes === 1 ? '' : 's'} (not readable as text).`)
  return lines.join('\n')
}
