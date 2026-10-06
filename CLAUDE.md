# AI Mock Interviewer

A voice-based mock interviewer for any job. Users upload a résumé and job description, pick a duration (10 / 30 / 45 / 60 min or custom 5–60), talk to an AI interviewer, and get a scored report with "stronger version" rewrites of their answers.

Full spec: `docs/SPEC.md` (read the relevant section before starting each phase). This file is the working summary for Claude Code.

## Hard rules

1. **$0 to run.** Use only free tiers and open-source software. Never add a dependency or service that costs money. If a free tier runs out, fall back to a local model; do not add a paid one.
2. **Never store audio or video.** Speech is transcribed live and discarded. The debrief feature is recall-only: never accept uploads of real interview recordings.
3. **Never invent experience** in "stronger version" rewrites. Use only facts from the user's résumé or answers; use placeholders like `[add the result you achieved]` for missing details.
4. **Respectful at every pressure level.** No insults, slurs, or personal attacks in pressure mode or role-plays.
5. **Scores are practice feedback**, not assessments. Show a disclaimer for licensed/specialized professions.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + Tailwind, LiveKit React components |
| In-browser | Monaco (code), Excalidraw (whiteboard), MediaPipe (body language, opt-in) |
| Backend | Flask (Python), JWT auth |
| Voice agent | LiveKit Agents (Python) |
| Audio transport | LiveKit Cloud free tier (or self-hosted LiveKit server) |
| LLM | Groq or Gemini free tier, behind `LLM_PROVIDER` env var |
| Speech-to-text | faster-whisper (local) default; Deepgram optional via `STT_PROVIDER` |
| Text-to-speech | Kokoro (local) default; Piper fallback |
| Database | MySQL 8 |
| Hosting | Oracle Cloud Always Free VM (Docker Compose + Caddy); frontend on Vercel |

## Repo layout

```
/frontend          React app (Vite)
  /src/pages       Setup, Interview, Report, Dashboard, StoryBank, Decoder, Debrief, Peer
  /src/components
  /src/lib         api client, livekit helpers
/backend           Flask API
  /app/routes      auth, documents, sessions, reports, stories, debriefs, peer, decoder
  /app/services    llm.py (provider switch), parsing.py, planning.py, scoring.py, stories.py, limits.py
  /app/prompts     one file per prompt (plan, rubric, followup, score, rewrite, story_extract, decoder, ...)
  /app/models      SQLAlchemy models
  /migrations
/agent             LiveKit Agents worker
  /modules         behavioral, resume_deepdive, technical, coding, system_design, case, roleplay, scenario, portfolio
  /modes           standard, reverse, pressure, peer, panel, negotiation
  timer.py         section budgets + nudges from backend
/evals             AI-candidate harness (strong / weak / rambling, across job fields)
docker-compose.yml
Caddyfile
```

## Core concepts

- **JD analysis** → field, seniority, competencies, which format modules fit.
- **Question plan** → sections with minute budgets that sum to the chosen duration, plus a reserve list of bonus questions. Editable by the user before starting.
- **Rubric** → per-session, built from JD competencies + universal criteria (structure, clarity, relevance).
- **Format modules** → reusable interviewer behaviors; any job = a mix of modules. New field = new mix, not new code.
- **Timer lives in the backend**, not the LLM. Backend sends nudges to the agent ("4 min left in section", "wrap up"). Agent never cuts off mid-sentence.
- **Reports generate after the session**, question by question in the background, never during the live call.

## Modes

standard · reverse (AI is the candidate) · pressure (levels 1–5, composure score) · peer (two humans + silent AI referee, both must consent) · debrief (recall-only, text saved, no audio) · panel (2–3 voices) · negotiation (recruiter role-play)

## Database tables

users · documents · jd_analyses · sessions · questions · answers (attempt_no for retries) · evaluations · reports · stories · debriefs · peer_rooms · question_bank (spaced repetition) · usage_limits

Flexible LLM output is stored in JSON columns. No table stores audio/video. Documents auto-delete after 30 days unless saved.

## Free-tier guards

- Per-user daily caps in `usage_limits` (start: 60 interview minutes, one 60-min session, 5 decoder runs).
- `services/llm.py` must catch rate-limit errors and fall back to the next provider.
- Default durations shown first: 10 and 30 minutes.

## Conventions

- Python: type hints, black formatting, one service function per responsibility.
- All LLM prompts live in `/backend/app/prompts` as plain text templates, never inline.
- LLM responses that feed the app must be JSON validated with Pydantic; retry once on invalid JSON.
- Secrets only in `.env` (never committed); provide `.env.example`.
- Every feature gets at least one test; LLM calls are mocked in tests.
- Commit after each working feature.

## Build phases

1. Foundation (repo, auth, schema, React shell)
2. Text-only brain (upload → JD analysis → plan → rubric; typed answers)
3. Voice interview (LiveKit agent, Whisper, Kokoro, captions)
4. Timer and sections (all durations, nudges, wrap-up, bonus questions)
5. Report and recommendations (scores, rewrites, delivery analytics, Try again)
6. Any-job support (modules, role-play, per-role rubrics)
7. Progress and story bank
8. Signature modes (decoder, debrief, reverse, pressure, peer)
9. Extras (coding, whiteboard, panel, body language, gap analysis, company research, negotiation, cheat sheet, thank-you email)
10. Deploy and harden (Oracle VM, Vercel, caps, eval harness, privacy controls)

**Current phase:** 1
