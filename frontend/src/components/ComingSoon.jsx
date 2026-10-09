export default function ComingSoon({ title, phase }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-slate-600">Coming in phase {phase}.</p>
    </section>
  )
}
