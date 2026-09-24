# Does multi-agent orchestration pay off in Claude Code? Two small benchmarks

Measurements from September 2026. Claude Code sessions were set up as an
orchestrator with worker subagents, and compared with a single session doing
the work alone. The task code and the orchestration template are private. This
repository has the method, the numbers, and the measurement script.

## TL;DR

- **Quality was the same** across every setup: every run fixed every ticket,
  and none broke an existing test.
- **Nobody delegated.** In 11 scored sessions, neither orchestrator started
  one of its worker agents. They judged the work too small to pay a subagent's
  fixed context cost.
- **Claude Fable 5.1 as orchestrator cost 1.9-3.0x as much as Claude Opus 5.5**
  for the same result. Speed was mixed.
- **Opus 5.5 working alone matched Opus 5.5 orchestrating** on cost and time.
  A blind two-reviewer code review ranked the solo solutions slightly higher.
- The template was changed accordingly: the main thread now runs on Opus 5.5,
  and "work directly" is the stated default. Delegation needs a reason the
  orchestrator can name.

One run per cell, on small and medium tasks. Treat this as a case study, not
a verdict.

## The setup under test

A private Claude Code project template. It configures a main-thread
**orchestrator agent** and three subagents:

| Role | Model | Effort | Purpose |
|---|---|---|---|
| Orchestrator (main thread) | Fable 5.1, later Opus 5.5 | high | plans, reviews, integrates |
| Opus worker | Opus 5.5 | high | complex or high-risk packages |
| Sonnet worker | Sonnet 5 | medium | straightforward packages |
| Read-only scout | Sonnet 5 | medium | broad code discovery |

The orchestrator's instructions include a delegation cost model. A subagent
starts a fresh context and does not share the parent's prompt cache, so it
pays several thousand tokens before doing any work. Delegating is supposed to
pay only when a package's own context use clearly exceeds that floor.

## Benchmark 1: a small tooling repository

Two tasks in a ~700-line Python repository (a validator and a hook with a
unit test suite). Both arms ran the same orchestrator instructions; only the
main-thread model differed.

- **Defect review:** five bugs that the repository really had in its history
  were re-introduced, and the tests that pinned them were removed. The
  original tests are the hidden check.
- **Small feature:** six numbered requirements, scored by hidden acceptance
  tests. One requirement deliberately contradicts an existing test; a good
  solution updates that test rather than weakening the requirement.

| Task | Main thread | Result | Cost | Time |
|---|---|---|---|---|
| Defect review | Fable 5.1 | 4/5 seeded bugs | $3.79 | 5.1 min |
| Defect review | Opus 5.5 | 3/5 (+1 half), plus 1 real bug nobody had seeded | $1.25 | 2.5 min |
| Small feature | Fable 5.1 | 4/4 | $2.05 | 3.4 min |
| Small feature | Opus 5.5 | 4/4 | $1.09 | 2.0 min |

The unseeded bug Opus found was real: a validator check compared a value with
itself and could never fire. It was reproduced and fixed afterwards.

## Benchmark 2: a real project, three arms

**Target:** a private Python project, about 35,000 lines with a 1,263-test
suite that runs in 90 seconds. It was only read; nothing was written to it.

**Tasks:** two bundles of four real bug fixes from the project's own history,
all from September 2026, after the models' training data. In each bundle the
four tickets touch disjoint files, so a parallel split would be possible. Each
fix was reverted at the source level only. The tests that the fix made pass
(26 in bundle A, 37 in B) were removed from the fixture and held back as
hidden checks. The whole suite doubles as a regression check.

**Arms:** identical code, tickets, project instructions, effort `high`, and
measurement. Only the orchestration differs:

| Arm | Main thread | Workers |
|---|---|---|
| F | orchestrator on Fable 5.1 | template workers |
| O | orchestrator on Opus 5.5 | template workers |
| S | plain session on Opus 5.5 | none; the Agent tool is denied in settings (`"permissions": {"deny": ["Agent"]}`) |

**Before any paid run**, a self-test checked every fixture in both directions.
The unfixed fixture had to score 0/4 with 0 regressions, and the project's
head had to score 4/4. A partial fix was checked by hand to score 1/4. The
self-test caught two fixture flaws before they cost anything:

- one ticket's tests imported a function that did not yet exist;
- the project's own test roll call would have leaked the hidden tests' names.

### Results

| Bundle | Arm | Tickets | Regressions | Cost | Time | Turns | Output tokens |
|---|---|---|---|---|---|---|---|
| A | F Fable orchestrates | 4/4 | 0 | $5.45 | 8.0 min | 27 | 27,469 |
| A | O Opus orchestrates | 4/4 | 0 | $2.78 | 11.5 min | 51 | 29,878 |
| A | S Opus solo | 4/4 | 0 | $3.30 | 15.6 min | 52 | 32,549 |
| B | F Fable orchestrates | 4/4 | 0 | $7.39 | 12.4 min | 46 | 45,081 |
| B | O Opus orchestrates | 4/4 | 0 | $3.01 | 10.1 min | 60 | 27,470 |
| B | S Opus solo | 4/4 | 0 | $2.85 | 8.8 min | 57 | 27,605 |

Totals per arm: F $12.84 and 20.4 min, O $5.79 and 21.6 min, S $6.15 and
24.4 min. A repeat of the A-O cell in a pilot cost $3.60, 29% more than the
same configuration above. That is the noise level to keep in mind.

### Blind code review

The hidden tests could not rank the arms further, so two reviewers scored the
six solutions for what tests do not measure: correctness beyond the tests,
design, test quality, documentation, and scope. The reviewers were Claude
Sonnet 5, which took part in no arm, and Claude Opus 5.5. They saw anonymised
trees: no history, no agent configuration, no measurement data, the same
instructions file, and randomised labels. The key was applied only after both
had reported.

| Bundle | Arm | Opus reviewer /25 | Sonnet reviewer /25 | Rank (both) |
|---|---|---|---|---|
| A | S Opus solo | 24 | 23 | 1 |
| A | O Opus orchestrates | 21 | 21 | 2 |
| A | F Fable orchestrates | 20 | 20 | 3 |
| B | S Opus solo | 25 | 25 | 1 |
| B | O Opus orchestrates | 22 | 24 | 2 |
| B | F Fable orchestrates | 20 | 19 | 3 |

- **Verified by running it:** the only correctness defect found in all six
  solutions was in a Fable solution. An API client handled "HTTP 200 but no
  usable task id" only for one of four malformed-response shapes, so the other
  three still produced the wrong verdict. The hidden tests covered only the one
  shape.
- **Correction to the reviewers:** both marked the Fable solution in bundle B
  down for adding a mutation-testing evidence file, calling it out of scope.
  The project's own instructions require exactly that: break each new test
  guard once on purpose and keep the verbatim output. It was the only solution
  of the six that followed that rule. Neither the tests nor the reviewers
  rewarded it.

## What we take from it

1. **The delegation cost model works as intended, perhaps too well for the
   workers to matter.** Four independent tickets in disjoint files, in a
   35k-line project, were still judged cheaper to do directly by both
   orchestrator models, in every run.
2. **The model in the main thread is what you pay for.** Fable 5.1 took
   fewer, larger turns and sometimes finished faster. It cost 2.0-2.5x as much
   in benchmark 2 and 1.9-3.0x in benchmark 1, for the same test results and
   a slightly weaker review score.
3. **Orchestration instructions did not help or hurt measurably** at this
   size. Opus solo and Opus orchestrating stayed within noise.
4. **Cache writes are the cost item to watch in short runs.** In benchmark 1
   (2-5 minute runs) they were 57-69% of the list price and reads only 7-15%.
   In benchmark 2's longer runs, reads grew to 37-47% for Opus, level with its
   writes (34-42%), while Fable's writes stayed at 50-60%. A 1-hour
   prompt-cache TTL writes at 2x the input price instead of 1.25x. For the
   benchmark 1 runs, the 5-minute TTL would have been 21-26% cheaper. For
   interactive sessions with pauses the trade-off can reverse.

## Side findings about Claude Code (as of September 2026)

- **The `opus` model alias resolves per provider.** The model configuration
  docs mapped it to Opus 5.5 on the Anthropic API, Claude Platform on AWS,
  Bedrock, and Google Cloud, but to Opus 4.6 on Microsoft Foundry. A subagent
  pinned with `model: opus` silently gets a different model there. Pin full
  IDs instead (`claude-opus-5-5`).
- **Opus 5.5 defaults to effort `medium`** in Claude Code when none is
  requested. Set `effort: high` explicitly if you want it.
- **Subagent `experimental: { cacheTtl: "1h" }` does take effect.** The
  transcripts show 1-hour cache writes for those subagents, and 5-minute writes
  for built-in ones.
- **The transcripts are good evidence.** `~/.claude/projects/**/*.jsonl`
  records the model that actually served every response, including subagents.
  Each subagent also has an `agent-<id>.meta.json` naming its agent type.

## Measuring your own sessions

`tools/measure_usage.py` (standard library only) summarises the current
machine's Claude Code transcripts into JSON. It reports:

- tokens per served model and role (main or subagent), counting each
  response once by its message id;
- each subagent's type and cache-write TTL;
- wall-clock time;
- counts of main-thread tool calls;
- commands that touched other git refs or clones, a leak check for
  benchmarks (extend it with the `BENCH_LEAK_EXTRA` regex).

The prices behind the cost column were list prices per million tokens:

| Model | Input | Output | Cache read | Cache write 5m | Cache write 1h |
|---|---|---|---|---|---|
| Fable 5.1 | 10 | 50 | 0.25 | 12.50 | 20 |
| Opus 5.5 | 4 | 20 | 0.20 | 5 | 8 |
| Sonnet 5 | 2 | 10 | 0.20 | 2.50 | 4 |

## Limits

- One run per cell, two for one cell, and the noise measured there was about
  30%.
- Tickets were precisely specified, which compresses quality differences.
- Neither benchmark made delegation happen, so they say nothing about
  whether workers pay off on large or parallel work.
- The reviewers are Claude models, and one of them is a contestant's model.
- The benchmark and its fixtures were built by a Claude Code session running
  one of the contestant models.

## License

MIT, see `LICENSE`.
