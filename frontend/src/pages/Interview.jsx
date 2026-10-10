import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import PlanEditor from '../components/PlanEditor'
import Recorder from '../components/Recorder'
import { Mascot } from '../components/Art'
import Timer from '../components/Timer'
import { api } from '../lib/api'
import { characterName, scenarioFor } from '../lib/modules'
import { answerModePref, canRecord, MAX_ANSWER_MS, setAnswerModePref } from '../lib/recording'
import { canSpeak, FILLERS, say, setVoicePref, voicePref, warmUpVoices } from '../lib/voice'

function speaker(t, plan) {
  const scenario = scenarioFor(plan, t.section)
  // The opening line follows the app's announcement; replies are the character's.
  if (scenario && t.is_follow_up) return `${characterName(scenario)} · role-play`
  return `Interviewer${t.is_follow_up ? ' · follow-up' : t.is_bonus ? ' · bonus' : ''}`
}

const BUBBLES = {
  interviewer: {
    avatar: 'from-brand-600 to-accent-500',
    box: 'bg-white ring-[#f1e6da]',
    label: 'text-brand-700',
  },
  character: {
    avatar: 'from-accent-300 to-accent-500',
    box: 'bg-accent-50 ring-accent-200',
    label: 'text-accent-700',
  },
}
// Each panel interviewer gets their own colour.
const PANEL_BUBBLES = {
  hm: { avatar: 'from-brand-500 to-brand-700', box: 'bg-white ring-brand-100', label: 'text-brand-700' },
  peer: { avatar: 'from-navy-500 to-navy-700', box: 'bg-navy-50 ring-navy-100', label: 'text-navy-700' },
  hr: { avatar: 'from-emerald-400 to-emerald-600', box: 'bg-emerald-50 ring-emerald-100', label: 'text-emerald-700' },
}

// "Priya · hiring manager" for a panel interviewer's line.
function panelLabel(panel, key) {
  const p = panel?.find((x) => x.key === key)
  return p ? `${p.name} · ${p.title.replace(/^(the|a|from the) /, '')}` : 'Interviewer'
}

// One interviewer (or role-play character) message, with an avatar.
function Bubble({ who = 'interviewer', panelist, label, children }) {
  const style = (panelist && PANEL_BUBBLES[panelist]) || BUBBLES[who]
  return (
    <div className="flex max-w-[88%] items-start gap-3">
      {who === 'interviewer' && !panelist ? (
        <Mascot className="mt-0.5 h-10 w-10 shrink-0" />
      ) : (
        <span
          aria-hidden="true"
          className={`mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br text-sm font-bold text-white shadow-sm ${style.avatar}`}
        >
          {label[0]}
        </span>
      )}
      <div className={`rounded-2xl rounded-tl-md p-4 shadow-sm ring-1 ${style.box}`}>
        <p className={`mb-1 text-xs font-semibold tracking-wide uppercase ${style.label}`}>{label}</p>
        <p className="leading-relaxed text-slate-800">{children}</p>
      </div>
    </div>
  )
}

function Transcript({ items, plan, panel }) {
  return (
    <ol className="space-y-5">
      {items.map((t) => {
        const scenario = scenarioFor(plan, t.section)
        // Each speaker's part in its own bubble ("Deal." from the character, then
        // the interviewer stepping out; panel interviewers handing over); older
        // messages have no segments.
        const parts =
          t.segments?.length > 1 || t.segments?.[0]?.panelist
            ? t.segments.map((seg) => ({
                who: seg.who,
                panelist: seg.who === 'interviewer' ? seg.panelist : undefined,
                text: seg.text,
                label:
                  seg.who === 'character' && scenario
                    ? `${characterName(scenario)} · role-play`
                    : seg.panelist
                      ? panelLabel(panel, seg.panelist)
                      : 'Interviewer',
              }))
            : [
                {
                  who: scenario && t.is_follow_up ? 'character' : 'interviewer',
                  text: t.interviewer,
                  label: speaker(t, plan),
                },
              ]
        return (
          <li key={t.question_id} className="space-y-3">
            {parts.map((p, i) => (
              <Bubble key={i} who={p.who} panelist={p.panelist} label={p.label}>
                {p.text}
              </Bubble>
            ))}
            {t.hint && (
              <Bubble label="Hint">
                <span aria-hidden="true">💡 </span>
                {t.hint}
              </Bubble>
            )}
            {t.answer && (
              <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-md bg-navy-800 p-4 text-white shadow-md shadow-navy-800/20">
                <p className="mb-1 text-xs font-semibold tracking-wide text-white/85 uppercase">
                  You{t.input_mode === 'voice' ? ' · transcribed' : ''}
                </p>
                <p className="leading-relaxed whitespace-pre-wrap">{t.answer}</p>
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

// Countdown for a typed answer under a pressure-mode time limit.
function TypedClock({ seconds, running, onTimeUp }) {
  const [left, setLeft] = useState(seconds)
  const fired = useRef(false)
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [running])
  useEffect(() => {
    if (left === 0 && !fired.current) {
      fired.current = true
      onTimeUp()
    }
  }, [left, onTimeUp])
  return (
    <p
      role="timer"
      aria-label="Time left for this answer"
      className={`chip ${left <= 10 ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600'}`}
    >
      {left > 0 ? `${left} s left` : "Time's up: sending what you have"}
    </p>
  )
}

function PlanStep({ session, setSession, onGreeting }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function savePlan(plan) {
    const data = await api(`/sessions/${session.id}/plan`, { method: 'PUT', body: plan })
    setSession(data.session)
  }

  async function start() {
    setError('')
    setBusy(true)
    try {
      const fire = session.voice?.provider === 'fire'
      const data = await api(`/sessions/${session.id}/start`, {
        method: 'POST',
        ...(fire && voicePref() ? { body: { speak: true } } : {}),
      })
      // The first question is spoken once the interview screen is up.
      onGreeting({ segments: data.session.transcript[0]?.segments, clips: data.speech })
      setSession(data.session)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const analysis = session.analysis || {}
  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">Step 2 of 2</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">{session.negotiation ? 'Your negotiation' : 'Your interview plan'}</h1>
        <p className="mt-1 text-slate-600">
          {session.role_title} · {session.duration_min} minutes · {session.difficulty} ·{' '}
          {session.persona} interviewer
        </p>
        {analysis.competencies?.length > 0 && (
          <p className="mt-2 text-sm text-slate-600">
            Focus: {analysis.competencies.map((c) => c.name).join(', ')}
          </p>
        )}
        {analysis.licensed_field && (
          <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800 ring-1 ring-amber-200">
            Feedback for licensed or specialized professions is for practice only, not a
            professional assessment.
          </p>
        )}
      </header>
      {session.negotiation ? (
        <p className="text-sm text-slate-600">
          A recruiter will call with an offer of {session.negotiation.offer}. You're aiming for{' '}
          {session.negotiation.target}.
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-600">
            Edit any question or the minutes per section, then start when you're ready.
          </p>
          <PlanEditor
            key={session.id}
            plan={session.plan}
            duration={session.duration_min}
            onSave={savePlan}
          />
        </>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="btn-primary"
      >
        {busy ? 'Starting…' : session.negotiation ? 'Start the call' : 'Start interview'}
      </button>
    </div>
  )
}

const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }

function LiveStep({ session, setSession, greeting }) {
  const [mode, setMode] = useState(answerModePref)
  // Bumped when a question has been asked (and spoken): in speak mode the
  // recorder starts by itself then.
  const [recordKey, setRecordKey] = useState(0)
  const modeRef = useRef(mode)
  modeRef.current = mode
  const said = useRef(0) // which speak() call is current
  const fireVoice = session.voice?.provider === 'fire'
  const persona = session.voice?.persona ?? session.persona
  const hasVoice = canSpeak() || fireVoice
  const [voiceOn, setVoiceOn] = useState(() => hasVoice && voicePref())
  const [speaking, setSpeaking] = useState(false)
  const [voiceFailed, setVoiceFailed] = useState(false)
  const [closing, setClosing] = useState(null)
  const voice = useRef(null) // what's playing now: { cancel }
  const lastSaid = useRef(null) // { segments, clips } for "Repeat"

  const [text, setText] = useState('')
  const [phase, setPhase] = useState('idle') // idle | transcribing | thinking
  const [error, setError] = useState('')
  const askedAt = useRef(0)
  const spoken = useRef(null) // {duration_ms} when the text box holds a transcript
  const bottom = useRef(null)
  const active = session.status === 'active'
  const busy = phase !== 'idle'
  const turns = session.transcript.length
  const roleplay = active ? scenarioFor(session.plan, session.timer?.section) : null
  const paused = Boolean(session.timer?.paused)
  // Pressure mode's per-answer limit (not in small talk, role-plays or Q&A).
  const answerLimit =
    session.pressure?.time_limit_sec &&
    !roleplay &&
    !['Ice-breaker', 'Your questions'].includes(session.transcript.at(-1)?.section)
      ? session.pressure.time_limit_sec
      : null
  const current = session.transcript.at(-1)
  const hintUsed = Boolean(current?.hint)
  // Small talk and "any questions for me?" get no hints.
  const noHints = !current || ['Ice-breaker', 'Your questions'].includes(current.section)

  useEffect(() => {
    askedAt.current = Date.now()
    bottom.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [turns])

  const stopSpeaking = useCallback(() => {
    voice.current?.cancel()
    voice.current = null
    setSpeaking(false)
  }, [])

  // The question is out (spoken, skipped, or voice is off): in speak mode, record.
  const questionReady = useCallback(() => {
    askedAt.current = Date.now()
    if (modeRef.current === 'voice') setRecordKey((k) => k + 1)
  }, [])

  const speak = useCallback(
    (message, { remember = true, onDone } = {}) => {
      if (!message?.segments?.length) return
      if (remember) lastSaid.current = message
      voice.current?.cancel()
      const turn = ++said.current
      const handle = say({ ...message, persona, panel: session.panel })
      voice.current = handle
      setSpeaking(true)
      handle.done.then((result) => {
        if (turn !== said.current) return // another message took over
        if (voice.current === handle) voice.current = null
        setSpeaking(false)
        setVoiceFailed(result?.ok === false)
        // Also after "Stop": the candidate wants to answer now.
        if (onDone) onDone()
        else askedAt.current = Date.now()
      })
    },
    [persona, session.panel],
  )

  // Speak the first question, and stop talking when the page goes away. (No
  // "already greeted" flag: React's dev double-mount cancels the first attempt.)
  useEffect(() => {
    warmUpVoices()
    if (!greeting) return () => voice.current?.cancel()
    if (voicePref() && hasVoice) speak(greeting, { onDone: questionReady })
    else questionReady()
    return () => voice.current?.cancel()
  }, [greeting, hasVoice, speak, questionReady])

  function toggleVoice() {
    const on = !voiceOn
    setVoiceOn(on)
    setVoicePref(on)
    if (!on) stopSpeaking()
  }

  function repeat() {
    // After a reload nothing has been said yet: read out the current question.
    speak(lastSaid.current ?? { segments: session.transcript.at(-1)?.segments }, {
      onDone: questionReady,
    })
  }

  // The interviewer's next message (after an answer or a skip).
  function handleReply(data) {
    const reply = { segments: data.turn.segments, clips: data.speech }
    const next = data.session.status === 'active' ? questionReady : undefined
    if (data.turn.action === 'wrap_up') setClosing(data.turn.message)
    setSession(data.session)
    if (voiceOn) speak(reply, { onDone: next })
    else {
      lastSaid.current = reply
      next?.()
    }
  }

  async function control(action) {
    setError('')
    stopSpeaking()
    try {
      const data = await api(`/sessions/${session.id}/${action}`, { method: 'POST' })
      if (action === 'skip') handleReply(data)
      else setSession(data.session)
      if (action === 'hint' && voiceOn) {
        speak({ segments: [{ who: 'interviewer', text: data.hint }] }, { remember: false, onDone: questionReady })
      } else if (action === 'hint' || action === 'resume') {
        questionReady()
      }
    } catch (err) {
      setError(err.message)
    }
  }

  async function ease(level) {
    setError('')
    try {
      setSession((await api(`/sessions/${session.id}/pressure`, { method: 'POST', body: { level } })).session)
    } catch (err) {
      setError(err.message)
    }
  }

  function timeUp() {
    // Typed answer in pressure mode: send what's there when the time runs out.
    if (text.trim() && !busy) sendTyped({ preventDefault() {} })
  }

  async function skip() {
    if (!window.confirm('Skip this question? It will be listed as unanswered in your report.')) return
    setPhase('thinking')
    try {
      await control('skip')
    } finally {
      setPhase('idle')
    }
  }

  async function sendTurn(answer, meta) {
    setPhase('thinking')
    try {
      const data = await api(`/sessions/${session.id}/turns`, {
        method: 'POST',
        // Only Fire voice needs the backend; the browser voice speaks the text.
        body: { text: answer, ...meta, ...(fireVoice && voiceOn ? { speak: true } : {}) },
      })
      setText('')
      spoken.current = null
      handleReply(data)
    } catch (err) {
      // Keep the answer (typed or transcribed) so it can be resent without re-recording.
      setError(err.message)
      setText(answer)
      if (meta.input_mode === 'voice') {
        spoken.current = { duration_ms: meta.duration_ms }
        setMode('text')
      }
    } finally {
      setPhase('idle')
    }
  }

  async function onRecorded(blob, durationMs) {
    setError('')
    setPhase('transcribing')
    if (voiceOn && !fireVoice) {
      // A quick "Mm-hm" covers the pause while the reply is written.
      const filler = FILLERS[Math.floor(Math.random() * FILLERS.length)]
      speak({ segments: [{ who: roleplay ? 'character' : 'interviewer', text: filler }] }, { remember: false })
    }
    const form = new FormData()
    const type = blob.type.split(';')[0]
    form.append('audio', blob, `answer.${EXT[type] ?? 'webm'}`)
    let transcript
    try {
      transcript = (await api(`/sessions/${session.id}/transcribe`, { method: 'POST', body: form })).text
    } catch (err) {
      setError(err.message)
      setPhase('idle')
      return
    }
    await sendTurn(transcript, {
      duration_ms: Math.min(durationMs, MAX_ANSWER_MS),
      input_mode: 'voice',
    })
  }

  function sendTyped(e) {
    e.preventDefault()
    if (!text.trim() || busy) return
    setError('')
    const meta = spoken.current
      ? { ...spoken.current, input_mode: 'voice' }
      : { duration_ms: Math.min(Date.now() - askedAt.current, MAX_ANSWER_MS), input_mode: 'text' }
    sendTurn(text, meta)
  }

  async function endEarly() {
    if (!window.confirm('End the interview now?')) return
    stopSpeaking()
    setSession((await api(`/sessions/${session.id}/end`, { method: 'POST' })).session)
  }

  return (
    <div className="space-y-6">
      <header className="card flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{session.role_title || 'Interview'}</h1>
          {active && <Timer timer={session.timer} running={!busy && !speaking && !paused} />}
        </div>
        {active && (
          <div className="flex flex-wrap items-center gap-4">
            {hasVoice && (
              <label className="flex cursor-pointer items-center gap-2 rounded-full bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-brand-100">
                <input type="checkbox" checked={voiceOn} onChange={toggleVoice} className="accent-brand-600" />
                Interviewer voice
              </label>
            )}
            <button
              type="button"
              onClick={endEarly}
              className="btn-link hover:text-red-600"
            >
              End interview
            </button>
          </div>
        )}
      </header>

      {active && session.transcript.at(-1)?.section === 'Your questions' && (
        <p className="rounded-2xl bg-navy-50 p-4 text-sm text-navy-800 ring-1 ring-navy-100">
          <span aria-hidden="true">💬 </span>
          <span className="font-bold">Your turn to ask.</span> Ask about the role, the team or next
          steps, like you would at the end of a real interview. Or just say you have no questions.
        </p>
      )}
      {active && session.pressure && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-gradient-to-r from-brand-50 to-accent-50 p-4 text-sm ring-1 ring-brand-200">
          <span className="font-bold text-brand-800">
            <span aria-hidden="true">🔥 </span>
            {session.pressure.level ? `Pressure level ${session.pressure.level}` : 'Pressure stopped'}
          </span>
          {session.pressure.time_limit_sec && (
            <span className="chip bg-white text-brand-700">{session.pressure.time_limit_sec} s per answer</span>
          )}
          {session.pressure.level > 0 && (
            <span className="ml-auto flex gap-2">
              <button type="button" onClick={() => ease(session.pressure.level - 1)} className="btn-secondary px-3 py-1">
                Ease off
              </button>
              <button type="button" onClick={() => ease(0)} className="btn-secondary px-3 py-1">
                Stop pressure
              </button>
            </span>
          )}
        </div>
      )}
      {roleplay && (
        <p className="rounded-2xl bg-gradient-to-r from-amber-50 to-orange-50 p-4 text-sm text-amber-900 ring-1 ring-amber-200">
          <span aria-hidden="true">🎭 </span>
          <span className="mr-1 font-bold">{session.negotiation ? 'Negotiation:' : 'Role-play:'}</span> the
          interviewer is playing {roleplay.character}. Your goal: {roleplay.goal}
          {session.negotiation && (
            <>
              {' '}
              (you're aiming for <span className="font-semibold">{session.negotiation.target}</span>)
            </>
          )}
        </p>
      )}
      <Transcript items={session.transcript} plan={session.plan} panel={session.panel} />
      {closing && !active && (
        <Bubble label="Interviewer">{closing}</Bubble>
      )}
      {speaking && !busy && (
        <p role="status" className="flex items-center gap-3 text-sm font-medium text-brand-700">
          <span className="flex items-end gap-0.5" aria-hidden="true">
            {[0, 150, 300].map((d) => (
              <span key={d} className="h-3 w-1 animate-bounce rounded-full bg-brand-500" style={{ animationDelay: `${d}ms` }} />
            ))}
          </span>
          <span>Interviewer is speaking…</span>
          <button type="button" onClick={stopSpeaking} className="btn-link">
            Stop
          </button>
        </p>
      )}
      {voiceFailed && voiceOn && active && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 ring-1 ring-amber-200">
          Your browser couldn't play the interviewer's voice (it may have no voices installed,
          or it blocked sound until you click). Try &ldquo;Repeat the question&rdquo;, or read
          the text.
        </p>
      )}
      {busy && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          {phase === 'transcribing' ? 'Listening back to your answer…' : 'Interviewer is thinking…'}
        </p>
      )}
      <div ref={bottom} />

      {active && paused ? (
        <div className="card flex flex-col items-center gap-4 p-8 text-center">
          <Mascot className="h-20 w-20" mood="wow" />
          <div>
            <p className="text-xl font-bold text-ink">Interview paused</p>
            <p className="mt-1 text-sm text-slate-600">
              The clock is stopped. Take a breath; resume when you're ready.
            </p>
          </div>
          <button type="button" onClick={() => control('resume')} className="btn-primary">
            <span aria-hidden="true">▶</span>Resume
          </button>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
        </div>
      ) : active ? (
        <div className="card space-y-4 p-5">
          {mode === 'voice' ? (
            <div className="space-y-2">
              <Recorder
                onRecorded={onRecorded}
                onStart={stopSpeaking}
                disabled={busy}
                autoStartKey={recordKey}
                limitMs={answerLimit ? answerLimit * 1000 : null}
              />
              <p className="text-xs text-slate-500">
                Recording starts by itself when the interviewer finishes the question.
              </p>
            </div>
          ) : (
            <form onSubmit={sendTyped} className="space-y-2">
              {answerLimit && (
                <TypedClock key={turns} seconds={answerLimit} running={!busy && !speaking} onTimeUp={timeUp} />
              )}
              <textarea
                aria-label="Your answer"
                rows={5}
                value={text}
                disabled={busy}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendTyped(e)
                }}
                placeholder="Type your answer… (Ctrl+Enter to send)"
                className="field"
              />
              <button
                type="submit"
                disabled={busy || !text.trim()}
                className="btn-primary"
              >
                Send answer
              </button>
            </form>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-slate-100 pt-3">
            {!noHints && (
              <button type="button" disabled={busy || hintUsed} onClick={() => control('hint')} className="btn-link">
                <span aria-hidden="true">💡 </span>
                {hintUsed ? 'Hint shown' : 'Get a hint'}
              </button>
            )}
            <button type="button" disabled={busy} onClick={skip} className="btn-link">
              <span aria-hidden="true">⏭ </span>Skip question
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                stopSpeaking()
                control('pause')
              }}
              className="btn-link"
            >
              <span aria-hidden="true">⏸ </span>Pause
            </button>
          {hasVoice && (
            <button type="button" disabled={busy} onClick={repeat} className="btn-link">
              <span aria-hidden="true">↻ </span>Repeat the question
            </button>
          )}
          {canRecord() && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setError('')
                spoken.current = null
                setMode((m) => {
                  const next = m === 'voice' ? 'text' : 'voice'
                  setAnswerModePref(next)
                  return next
                })
              }}
              className="btn-link"
            >
              {mode === 'voice' ? 'Type instead' : 'Speak instead'}
            </button>
          )}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl bg-gradient-to-br from-brand-50 via-accent-50 to-navy-50 p-6 ring-1 ring-brand-100">
          <p className="text-lg font-bold text-slate-900">
            <span aria-hidden="true">🎉 </span>
            <span>Interview finished.</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Your report scores each answer and shows a stronger version of it.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <Link
              to={`/report/${session.id}`}
              className="btn-primary"
            >
              See your report
            </Link>
            <Link to="/setup" className="btn-link">
              Start another interview
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Interview() {
  const { id } = useParams()
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')
  const location = useLocation()
  const navigate = useNavigate()
  // Set when Setup started the interview directly ("Start right away").
  const [greeting, setGreeting] = useState(() => location.state?.greeting ?? null)

  useEffect(() => {
    // Don't greet again if the page is reloaded later.
    if (location.state?.greeting) navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  const load = useCallback(() => {
    api(`/sessions/${id}`)
      .then((data) => setSession(data.session))
      .catch((err) => setError(err.message))
  }, [id])

  useEffect(load, [load])

  if (error) return <p role="alert" className="text-red-600">{error}</p>
  if (!session) return <p className="text-slate-500">Loading…</p>
  if (session.status === 'planned')
    return <PlanStep session={session} setSession={setSession} onGreeting={setGreeting} />
  return <LiveStep session={session} setSession={setSession} greeting={greeting} />
}
