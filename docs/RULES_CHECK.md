# Rules check log

After every build phase, the app is checked against [INTERVIEWER_RULES.md](INTERVIEWER_RULES.md).
Each rule area is marked ✅ met, ⚠️ partly met, ❌ not met, or ⏳ planned for a later phase.
Every ⚠️ / ❌ gets a ticket (`orchestration.tickets`); the next check confirms it.

---

## Check after Phase 6 (2026-10-10) — first check, covers Phases 1–6

| Area | Status | Evidence / gap |
|---|---|---|
| Core behavior | ✅ | One question per turn; plan and rubric from résumé + JD + level + type; session history passed to every turn; no ideal answers before an attempt; neutral acknowledgements only (praise filtered); scores labelled practice feedback. |
| Interview preparation | ⚠️ | JD analysis, plan with minute budgets, rubric, editable plan ("Review the questions first") all built. Gap: prompts don't say "don't assume a missing résumé skill means a missing skill" — **T-42**. |
| During the interview | ⚠️ | Module-appropriate questions, follow-ups that probe vague or missing parts, backend timer moves on and wraps up, Repeat and Try again, failed transcription keeps the answer and offers typing. Gap: no **hint, pause/resume, skip** controls — **T-40**. |
| Adaptive difficulty | ⚠️ | Entry / mid / senior expectations are used in planning, turns and scoring. Gaps: challenge doesn't rise after strong answers — **T-43**; hints on request — **T-40**; "never equate nervousness/accent with lack of ability" isn't stated to the scorer — **T-42**. |
| Scoring | ⚠️ | Per-session rubric, per-criterion comments, weighted scores computed in code, temperature 0, near-empty answers score 1, retries compared on the same criteria, invented claims caught and repaired, transcription slips forgiven, disclaimer shown. Gaps: "don't penalize concise but correct", "missing evidence ≠ lack of knowledge" not in the prompt — **T-42**; uncertainty (e.g. low-confidence transcripts) not labelled — **T-41**. |
| Answer coaching | ⚠️ | Missing points, weak moments, grounded stronger version with placeholders, "what changed and why", STAR check, tips, delivery tips, Try again with before/after. Gap: no explicit "what you did well" list (only the one-line summary) — **T-41**. |
| Interviewer personalities | ✅ | Friendly / neutral / tough change tone, openings, sign-offs and voice only; the scorer never sees the persona. |
| Interview modes | ✅ | Only implemented formats that fit the job are offered at setup. Unbuilt modes (story bank, decoder, debrief) are labelled "Coming soon". |
| Final report | ⚠️ | Question scores, overall score and verdict reasoning, top 3 takeaways, highlighted weak moments, stronger versions, delivery analytics only from measured data (pace for spoken answers only). Gaps: no session-level competency feedback, no recommended exercises, unanswered planned questions and failed evaluations aren't listed — **T-41**. |
| Story bank and progress | ⏳ | Phase 7. The dashboard already shows progress (scores over time, roles, skill averages). |
| Safety and privacy | ⚠️ | Fire key only in backend `.env`; no audio stored (clips dropped after transcription); documents expire after 30 days and can be deleted; licensed-profession disclaimer; respectful-pressure rules in prompts. Gaps: no explicit "avoid discriminatory, invasive or irrelevant questions" instruction — **T-42**; expired documents are hidden but not yet purged (Phase 10). Debrief (no recordings) is Phase 8. |

**Open from this check:** T-40, T-41, T-42, T-43.

---

## Re-check after fixing the Phase 6 gaps (2026-10-10)

| Area | Status | What changed |
|---|---|---|
| Interview preparation | ✅ | Plan prompt: don't assume a skill is missing because the résumé doesn't list it — ask about it (**T-42**). |
| During the interview | ✅ | **Get a hint** (one per question, noted in the score), **Skip question** (listed as unanswered), **Pause / Resume** (clock stops) — **T-40**. |
| Adaptive difficulty | ✅ | Interviewer raises the challenge one step after strong, complete answers and never after a struggle; gives fair hints on request (**T-43**); never treats nervousness, accent or limited experience as lack of ability (**T-42**). |
| Scoring | ✅ | Scorer: evidence-based comments across relevance, accuracy, reasoning, specificity, structure, ownership, impact, role alignment; missing evidence ≠ lack of knowledge; no penalty for concise-but-correct answers, accent or nervousness (**T-42**); each answer labelled "AI coach's judgment" with a confidence level and reason (**T-41**). |
| Answer coaching | ✅ | "What you did well" (1–3 specific strengths) added to each answer (**T-41**). |
| Final report | ✅ | Competency averages, 2–3 recommended exercises, "Questions you didn't get to", and "Couldn't be scored" on failed evaluations (**T-41**). |
| Safety and privacy | ⚠️ | Plan, turn and role-play prompts forbid discriminatory, invasive or irrelevant questions (**T-42**). Still planned: purge expired documents (Phase 10); debrief without recordings (Phase 8). |
| Story bank and progress | ⏳ | Phase 7. |

Core behavior, personalities and modes remain ✅. **Open from this check:** none (the ⚠️/⏳ items are scheduled phases).
