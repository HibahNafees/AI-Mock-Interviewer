export default function ComingSoon({ title, phase }) {
  return (
    <section className="card p-8 text-center">
      <p className="eyebrow">Coming soon</p>
      <h1 className="mt-2 text-3xl font-extrabold text-slate-900">{title}</h1>
      <p className="mt-2 text-slate-600">Coming in phase {phase}.</p>
    </section>
  )
}
