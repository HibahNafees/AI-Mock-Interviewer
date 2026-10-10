import { expect, it } from 'vitest'
import { describeScene } from './whiteboard'

it('turns boxes, labels and arrows into text', () => {
  const scene = [
    { id: 'a', type: 'rectangle', boundElements: [{ id: 'ta', type: 'text' }] },
    { id: 'ta', type: 'text', text: 'API\ngateway', containerId: 'a' },
    { id: 'b', type: 'ellipse' },
    { id: 'c', type: 'rectangle', isDeleted: true },
    { id: 'x', type: 'arrow', startBinding: { elementId: 'a' }, endBinding: { elementId: 'b' } },
    { id: 'tx', type: 'text', text: 'reads', containerId: 'x' },
    { id: 'y', type: 'arrow', startBinding: { elementId: 'b' } },
    { id: 'n', type: 'text', text: '10k requests / s' },
    { id: 'f', type: 'freedraw' },
  ]
  expect(describeScene(scene)).toBe(
    [
      'Components: API gateway, unlabeled circle 1',
      'Connections: API gateway → unlabeled circle 1 ("reads"); unlabeled circle 1 → nothing',
      'Notes: "10k requests / s"',
      'Plus 1 freehand line (not readable as text).',
    ].join('\n'),
  )
})

it('is empty for an empty board', () => {
  expect(describeScene([])).toBe('')
  expect(describeScene([{ id: 'a', type: 'rectangle', isDeleted: true }])).toBe('')
})
