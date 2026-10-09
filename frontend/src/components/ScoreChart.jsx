import { useRef, useState } from 'react'

const W = 560
const H = 200
const PAD = { top: 16, right: 16, bottom: 28, left: 32 }
const LINE = '#e56553' // brand-600; validated ≥3:1 on the white card

function fmtDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Overall score per interview over time (1–5). One series, so no legend: the card's
// title names it. Hover (or focus + arrow keys) shows the value; a table is
// provided for screen readers.
export default function ScoreChart({ history }) {
  const [active, setActive] = useState(null)
  const svg = useRef(null)
  const n = history.length
  const x = (i) => PAD.left + (n === 1 ? (W - PAD.left - PAD.right) / 2 : (i * (W - PAD.left - PAD.right)) / (n - 1))
  const y = (s) => PAD.top + ((5 - s) / 4) * (H - PAD.top - PAD.bottom)
  const points = history.map((h, i) => ({ ...h, cx: x(i), cy: y(h.score) }))
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${p.cx},${p.cy}`).join(' ')

  function pick(clientX) {
    const box = svg.current.getBoundingClientRect()
    const vx = ((clientX - box.left) / box.width) * W
    let best = 0
    points.forEach((p, i) => {
      if (Math.abs(p.cx - vx) < Math.abs(points[best].cx - vx)) best = i
    })
    setActive(best)
  }

  const a = active != null ? points[active] : null
  return (
    <div className="relative">
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-none select-none"
        role="img"
        aria-label={`Overall score for your last ${n} interview${n > 1 ? 's' : ''}`}
        tabIndex={0}
        onMouseMove={(e) => pick(e.clientX)}
        onMouseLeave={() => setActive(null)}
        onTouchStart={(e) => pick(e.touches[0].clientX)}
        onTouchMove={(e) => pick(e.touches[0].clientX)}
        onFocus={() => setActive(n - 1)}
        onBlur={() => setActive(null)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setActive((i) => Math.max(0, (i ?? n - 1) - 1))
          if (e.key === 'ArrowRight') setActive((i) => Math.min(n - 1, (i ?? 0) + 1))
        }}
      >
        {[1, 2, 3, 4, 5].map((s) => (
          <g key={s}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(s)} y2={y(s)} stroke="#efe4d8" strokeDasharray={s === 1 ? '' : '3 4'} />
            <text x={PAD.left - 10} y={y(s) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">
              {s}
            </text>
          </g>
        ))}
        {n > 0 && (
          <>
            <text x={points[0].cx} y={H - 6} textAnchor={n === 1 ? 'middle' : 'start'} className="fill-slate-400 text-[11px]">
              {fmtDate(points[0].date)}
            </text>
            {n > 1 && (
              <text x={points[n - 1].cx} y={H - 6} textAnchor="end" className="fill-slate-400 text-[11px]">
                {fmtDate(points[n - 1].date)}
              </text>
            )}
          </>
        )}
        {a && <line x1={a.cx} x2={a.cx} y1={PAD.top} y2={H - PAD.bottom} stroke="#b7bdcb" strokeWidth="1" />}
        {n > 1 && <path d={path} fill="none" stroke={LINE} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
        {points.map((p, i) => (
          <circle
            key={p.session_id}
            cx={p.cx}
            cy={p.cy}
            r={active === i ? 6 : 4}
            fill={LINE}
            stroke="#fff"
            strokeWidth="2"
          />
        ))}
      </svg>
      {a && (
        <div
          role="status"
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-lg"
          style={{ left: `${(a.cx / W) * 100}%`, top: `${(a.cy / H) * 100}%`, marginTop: -10 }}
        >
          <p className="font-bold tabular-nums">{a.score.toFixed(1)} / 5</p>
          <p className="text-white/70">
            {a.role} · {fmtDate(a.date)}
          </p>
        </div>
      )}
      <table className="sr-only">
        <caption>Overall score per interview</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>Role</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.session_id}>
              <td>{h.date}</td>
              <td>{h.role}</td>
              <td>{h.score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
