import { useEffect, useState } from 'react'

function clock(sec) {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Counts down locally from the backend's timer state; the backend stays the authority.
export default function Timer({ timer, running }) {
  const [hidden, setHidden] = useState(false)
  const [ticked, setTicked] = useState(0)

  useEffect(() => {
    setTicked(0)
    if (!running) return
    const id = setInterval(() => setTicked((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [timer, running])

  if (!timer) return null
  const remaining = timer.remaining_sec - ticked
  const sectionLeft = timer.section_remaining_sec - ticked

  return (
    <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
      {hidden ? null : (
        <>
          <span
            aria-label="Time left"
            className={`rounded-lg px-2.5 py-0.5 font-mono text-lg font-semibold tabular-nums ${
              remaining <= 60 ? 'bg-rose-100 text-rose-700' : 'bg-violet-100 text-violet-700'
            }`}
          >
            {clock(remaining)}
          </span>
          {timer.section && (
            <span className={sectionLeft > 0 ? 'text-slate-600' : 'font-medium text-rose-600'}>
              {timer.section}
              {sectionLeft > 0 ? ` · ${clock(sectionLeft)} left` : ' · over time'}
            </span>
          )}
        </>
      )}
      <button
        type="button"
        onClick={() => setHidden((h) => !h)}
        className="btn-link text-xs"
      >
        {hidden ? 'Show timer' : 'Hide timer'}
      </button>
    </div>
  )
}
