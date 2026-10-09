import { useState } from 'react'
import { Logo } from './Layout'

export default function AuthForm({ title, fields, submitLabel, onSubmit, footer }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((f) => [f.name, ''])))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await onSubmit(values)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 px-4 py-10">
      <div className="text-center">
        <Logo />
        <p className="mt-3 text-sm text-slate-600">Practice interviews for any job, out loud.</p>
      </div>
      <form onSubmit={handleSubmit} className="card w-full max-w-sm space-y-4 p-7">
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {fields.map((f) => (
          <label key={f.name} className="block text-sm">
            <span className="font-medium text-slate-700">{f.label}</span>
            <input
              type={f.type}
              name={f.name}
              autoComplete={f.autoComplete}
              required
              minLength={f.minLength}
              value={values[f.name]}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              className="field mt-1.5"
            />
          </label>
        ))}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="btn-primary w-full"
        >
          {busy ? 'Please wait…' : submitLabel}
        </button>
        <p className="text-center text-sm text-slate-600">{footer}</p>
      </form>
    </div>
  )
}
