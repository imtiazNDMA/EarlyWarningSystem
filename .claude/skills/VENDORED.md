# Vendored skills

These skills come from [mattpocock/skills](https://github.com/mattpocock/skills)
(MIT, see `LICENSE`). They are vendored rather than installed as a plugin so the
version is pinned, the set is limited to what this repo can actually use, and
the examples match this stack.

- **Upstream commit:** `84fdeff` (plugin version `1.2.3`)
- **Vendored on:** 2026-10-08

## What was kept

16 of 35 upstream skills:

| Skill | Purpose |
| --- | --- |
| `tdd` | Red-green-refactor, integration-style tests |
| `diagnosing-bugs` | Diagnosis loop for hard bugs and performance regressions |
| `code-review` | Review changes since a fixed point |
| `codebase-design` | Deep-module vocabulary, seam placement |
| `domain-modeling` | `CONTEXT.md` glossary and ADRs |
| `research` | Investigate against primary sources, capture as Markdown |
| `prototype` | Throwaway prototype to answer a design question |
| `grilling` | Stress-test a plan or decision |
| `to-spec` | Turn a conversation into a spec on the issue tracker |
| `to-tickets` | Break a plan into tracer-bullet tickets |
| `triage` | Move issues through the triage state machine |
| `wayfinder` | Plan work too large for one session as a shared map |
| `implement` | Implement from a spec or set of tickets |
| `handoff` | Compact a conversation into a handoff document |
| `resolving-merge-conflicts` | Resolve an in-progress merge or rebase |
| `writing-for-agents` | Writing skills, `CLAUDE.md` and `AGENTS.md` |

## What was dropped, and why

- **Not this stack:** `setup-pre-commit` (Husky, lint-staged), `migrate-to-shoehorn`
  (`@total-typescript/shoehorn`), `setup-ts-deep-modules` (dependency-cruiser),
  `scaffold-exercises` (course authoring). This repo has no root `package.json`.
- **One-shot, already run:** `setup-matt-pocock-skills`. Its output is
  `docs/agents/`, which is committed.
- **Unfinished upstream:** everything under `in-progress/` and `deprecated/`.
- **Superseded or marginal here:** `ask-matt` (routing lives in `CLAUDE.md`),
  `grill-me` (duplicate of `grilling`), `improve-codebase-architecture` (HTML
  report flow), `wizard`, `teach`, `to-questionnaire`, `wait-what`,
  `grill-with-docs`.

Each dropped skill still costs a description line in every request while
installed, which is why the set is trimmed rather than mirrored.

## Local adaptations

`agents/openai.yaml` was removed from every skill — it targets a different
harness. Beyond that, 17 edits were applied. **Re-apply these after any upstream
refresh.**

Examples translated from TypeScript to this repo's Python idiom:

- `tdd/tests.md` — all four example blocks now use pytest and the alert
  lifecycle / screening code.
- `tdd/mocking.md` — dependency injection shown with
  `OpenMeteoForecastClient(http, base_url)` and `httpx.MockTransport`;
  SDK-style interfaces shown as typed methods. Noted that this repo mocks no
  database, using a real disposable Postgres per test.
- `codebase-design/SKILL.md` — the two testability examples now use
  `run_cycle` and `decide`; the "interface" framing mentions Python `Protocol`
  and ABC alongside TypeScript's `interface`.

References to skills that are not vendored, repointed so they stay actionable:

- Six `/setup-matt-pocock-skills` prompts (in `code-review`, `to-spec`,
  `to-tickets` ×2, `triage`, `wayfinder`) now point directly at
  `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.
- `diagnosing-bugs` handed architectural findings to
  `/improve-codebase-architecture`; it now hands them to `/codebase-design`.

Deliberately left alone: `prototype`'s command list (already language-agnostic)
and the example file paths in `triage/AGENT-BRIEF.md` (illustrative only).

## Refreshing from upstream

```bash
git clone --depth 1 https://github.com/mattpocock/skills /tmp/mp-skills
# copy the 16 directories above, flattened, dropping each agents/ folder
# then re-apply the 17 local adaptations listed above
```

Check the upstream diff for new skills worth adding and for changes to the ones
kept here.
