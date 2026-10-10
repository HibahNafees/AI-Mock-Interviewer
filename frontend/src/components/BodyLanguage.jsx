// The opt-in camera panel for body language feedback.
export default function BodyLanguage({ body }) {
  const { status, error, videoRef, enable, disable } = body
  const on = status === 'on' || status === 'loading'
  return (
    <section className="card space-y-3 p-4" aria-label="Body language">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold text-ink">
            <span aria-hidden="true">📷 </span>Body language feedback
          </h2>
          <p className="text-xs text-slate-500">
            Optional. Eye contact, posture and fidgeting are measured on this device; the video never leaves it.
            Only a few percentages per answer are saved.
          </p>
        </div>
        <button type="button" onClick={on ? disable : enable} className="btn-secondary px-3 py-1">
          {on ? 'Turn camera off' : 'Turn camera on'}
        </button>
      </div>
      {/* Always mounted so the stream has somewhere to go; hidden until on. */}
      <video
        ref={videoRef}
        muted
        playsInline
        aria-label="Your camera"
        className={`${on ? 'block' : 'hidden'} h-36 w-48 -scale-x-100 rounded-xl bg-slate-900 object-cover`}
      />
      {status === 'loading' && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          Starting the camera and loading the model…
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  )
}
