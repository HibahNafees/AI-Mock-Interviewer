import { Excalidraw } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'

// The system-design whiteboard. Only a text description of the sketch (boxes,
// labels, arrows) is sent with each answer; the drawing stays in the browser.
export default function Whiteboard({ onChange }) {
  return (
    <section className="card space-y-3 p-4" aria-label="Whiteboard">
      <h2 className="font-semibold text-ink">
        <span aria-hidden="true">🧭 </span>Whiteboard
      </h2>
      <div className="h-[420px] overflow-hidden rounded-xl ring-1 ring-slate-200">
        <Excalidraw
          onChange={(elements) => onChange(elements)}
          UIOptions={{ canvasActions: { loadScene: false, saveToActiveFile: false, export: false } }}
        />
      </div>
      <p className="text-xs text-slate-500">
        Draw boxes for components, type a name inside each (double-click a box) and connect them with arrows. The
        interviewer reads the names and arrows, not the drawing.
      </p>
    </section>
  )
}
