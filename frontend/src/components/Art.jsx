// Original illustrations (inline SVG, no external images): the app's mascot "Echo",
// a friendly speech bubble with a headset, and a few scenes built around it.

export function Mascot({ className = 'h-24 w-24', mood = 'happy', title }) {
  const mouth =
    mood === 'wow' ? (
      <ellipse cx="60" cy="70" rx="6" ry="7" fill="#882a1e" />
    ) : (
      <path d="M49 66c4 7 18 7 22 0" stroke="#882a1e" strokeWidth="4" strokeLinecap="round" fill="none" />
    )
  return (
    <svg viewBox="0 0 120 120" className={className} role={title ? 'img' : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      {/* shadow */}
      <ellipse cx="60" cy="112" rx="30" ry="5" fill="#101319" opacity="0.08" />
      {/* bubble body with a tail */}
      <path
        d="M60 14c26 0 44 16 44 40s-18 40-44 40c-6 0-12-1-17-3l-14 9 3-15C21 78 16 67 16 54c0-24 18-40 44-40z"
        fill="url(#echoBody)"
      />
      <path d="M38 26c8-5 17-7 26-6" stroke="#fff" strokeWidth="5" strokeLinecap="round" opacity="0.5" fill="none" />
      {/* headset */}
      <path d="M22 50c0-24 17-38 38-38s38 14 38 38" stroke="#023350" strokeWidth="6" fill="none" strokeLinecap="round" />
      <rect x="14" y="44" width="12" height="20" rx="6" fill="#023350" />
      <rect x="94" y="44" width="12" height="20" rx="6" fill="#023350" />
      <path d="M20 63c2 12 10 17 22 17" stroke="#023350" strokeWidth="4" fill="none" strokeLinecap="round" />
      <circle cx="45" cy="80" r="5" fill="#fdc458" stroke="#023350" strokeWidth="3" />
      {/* face */}
      <ellipse cx="47" cy="50" rx="5" ry="6.5" fill="#101319" />
      <ellipse cx="73" cy="50" rx="5" ry="6.5" fill="#101319" />
      <circle cx="49" cy="47.5" r="1.8" fill="#fff" />
      <circle cx="75" cy="47.5" r="1.8" fill="#fff" />
      <ellipse cx="38" cy="62" rx="6" ry="4" fill="#ffa798" opacity="0.8" />
      <ellipse cx="82" cy="62" rx="6" ry="4" fill="#ffa798" opacity="0.8" />
      {mouth}
      <defs>
        <linearGradient id="echoBody" x1="20" y1="14" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop stopColor="#fd7c68" />
          <stop offset="1" stopColor="#e56553" />
        </linearGradient>
      </defs>
    </svg>
  )
}

// Echo next to a mini report card, for the dashboard hero.
export function HeroScene({ className = '' }) {
  return (
    <div className={`relative ${className}`} aria-hidden="true">
      <div className="absolute top-2 right-0 w-56 rotate-3 rounded-3xl bg-white p-4 shadow-xl shadow-ink/10">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold tracking-wider text-brand-600 uppercase">Answer score</span>
          <span className="chip bg-emerald-100 text-emerald-700">4.6 / 5</span>
        </div>
        <ul className="mt-3 space-y-2 text-xs text-slate-600">
          {['Clear structure', 'Specific result', 'Confident pace'].map((t) => (
            <li key={t} className="flex items-center gap-2">
              <span className="grid h-4 w-4 place-items-center rounded-full bg-emerald-500 text-[10px] text-white">✓</span>
              {t}
            </li>
          ))}
        </ul>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-accent-100">
          <div className="h-full w-[92%] rounded-full bg-gradient-to-r from-brand-400 to-accent-400" />
        </div>
      </div>
      <div className="absolute bottom-3 left-2 -rotate-6 rounded-2xl bg-navy-800 px-3 py-2 text-xs font-semibold text-white shadow-lg">
        🎙️ Tell me about a time…
      </div>
      <Mascot className="absolute bottom-0 left-1/2 h-36 w-36 -translate-x-1/2 drop-shadow-xl" />
      <span className="absolute top-6 left-6 text-2xl">✨</span>
    </div>
  )
}

// Small rounded "3D" tile with an emoji, for stat cards and feature lists.
export function IconTile({ children, tone = 'brand', className = 'h-11 w-11 text-xl' }) {
  const tones = {
    brand: 'from-brand-100 to-brand-200 shadow-brand-200',
    accent: 'from-accent-100 to-accent-300 shadow-accent-200',
    navy: 'from-navy-100 to-navy-200 shadow-navy-200',
    green: 'from-emerald-100 to-emerald-200 shadow-emerald-200',
  }
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-2xl bg-gradient-to-br shadow-[inset_0_-3px_0_0_rgb(0_0_0/0.06)] ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
