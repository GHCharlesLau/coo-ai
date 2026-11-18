---
name: coo-intake
description: Turns a raw user demand into a complete campaign brief.json. Use only during the COO AI intake stage, before research or strategy.
---

# Intake

## When to use

When the orchestrator is on stage `intake` and the only source material is the user demand (plus any user notes).

## Required inputs

- User demand text
- `campaign_id` from context
- Optional user notes

## Procedure (do not skip)

1. Read the demand. Extract brand, offer, audience, outcome, timing, and budget if present.
2. Write a working title.
3. State 1–3 objectives. Each gets a stable `id` (`obj_...`), a statement, and a metric/target/timeframe when the demand supports it.
4. Fill `audience.primary`. Add secondary and insights only if grounded in the demand or an explicit assumption later.
5. Write `success_definition` as a sentence a COO could check after the campaign.
6. Record constraints (`budget`, `timeline`, `channel`, `legal`, `brand`, `other`).
7. Record `intake_topics.event_date`, `.budget`, `.brand_guardrails`, `.key_competitors`, `.key_challenges`, and `.blacklisted_terms`. Ask about each. Explicitly record unknown/not-set answers instead of inventing them. `event_date` is conditional: for an event-led demand (event, summit, conference, festival, forum, expo, ceremony, activation, roadshow, leaders week, host year) give the date, a rebaseline, or an explicit unknown; for brand-only work write `not_applicable`. Objective and audience are captured in their dedicated fields. Extract exact prohibited concepts into `forbidden_associations` and exact words/phrases into `forbidden_phrases` when the client supplies them.
8. List `open_questions` only for facts the client must provide (budget cap, legal clearance, spokesperson, brand-mandated lines). Use `unanswered` when the user must reply. Defer only sign-off facts (budget owner, legal clearance) with a `defer_reason`.
9. Do **not** open-question public look-uppable facts (host economy, published calendar, official venues). Research will look those up. Do not defer them either.
10. Copy `user_demand` verbatim into the artifact. Set `campaign_id` to the id in context.
11. Self-check against the schema below, then emit `brief.json`.

## Output schema (`brief.json`)

```
campaign_id: string
title: string
brand: string
user_demand: string
objectives: [{id, statement, metric?, target?, timeframe?}]
audience: {primary, secondary?, insights[]}
offer: string
success_definition: string
constraints: [{kind, detail}]
open_questions: [{id, question, status: unanswered|answered|deferred, answer?, defer_reason?}]
intake_topics: {event_date, budget, brand_guardrails, key_competitors, key_challenges, blacklisted_terms}
forbidden_associations: [string]
forbidden_phrases: [string]
notes: string
```

## Self-check

- At least one objective with a non-empty statement
- Non-empty title, brand, offer, audience.primary, success_definition
- Deferred items are sign-off only, never host/calendar/venue
- Every required intake topic has a client answer or an explicit unknown/not-set response (`event_date` is required only for event-led demands)
- Event-led demands never use `not_applicable` for `event_date`
- Never fill a missing date, cap, guardrail, competitor, challenge, or blacklist item with an invented client answer
- No channels, tactics, media mix, or creative lines

## Must not do

- Do not write the proposal.
- Do not invent research findings.
- Do not answer questions you do not know; leave them unanswered or deferred.
- Do not defer a public fact so the pipeline can skip research.
