// Code or a whiteboard sketch the candidate showed with an answer.
export default function WorkView({ work, dark = false }) {
  if (!work) return null
  const code = work.kind === 'code'
  return (
    <details className={`mt-2 rounded-xl text-sm ${dark ? 'bg-white/10' : 'bg-surface ring-1 ring-slate-200'}`}>
      <summary className="cursor-pointer px-3 py-2 font-medium">
        {code ? `Your code (${work.language})` : 'Your sketch, as the interviewer read it'}
      </summary>
      <pre className="overflow-x-auto px-3 pb-3 font-mono text-xs leading-relaxed whitespace-pre">{work.content}</pre>
      {work.output && (
        <>
          <p className="px-3 text-xs font-semibold">Output when you ran it</p>
          <pre className="overflow-x-auto px-3 pb-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">{work.output}</pre>
        </>
      )}
    </details>
  )
}
