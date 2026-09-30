# Skill: circular chain-of-thought — signatures, intervention, response

## The failure pattern, precisely

A model uses the plan-audit-map tool for the first stretch of a solution,
then silently stops calling it and drifts back to native chain-of-thought.
The second half is uninformed by everything the first half learned —
including its errors — so it re-derives, fails the same way, and loops.
The model cannot see this happening: its "checks" are pattern-matches
against its own output, not checks. Visible-CoT-can-lie is the operating
assumption; you need signals outside the model's self-report.

## Signatures (any two = intervene)

- The same fix or check proposed twice with different wording.
- "Verification" by re-reading its own reasoning instead of running
  something deterministic (a test, a diff, a count, a build).
- Retry/hedge vocabulary with no new information between attempts:
  "let me try again", "wait, actually", "hmm", "one more attempt",
  "maybe the cache", "let me re-check".
- Wire-log evidence: ≥ 10 MCP events since the last `tools/call` while
  the conversation kept going (the quantitative "forgot the tool" sign).
- Measured repetition: a large share of the trace's 5-grams occurring
  more than once; a long repeated token block.

## The two-round-trip protocol (human side)

Copy the agent's last few messages (just the circling part, a screenful
is plenty), paste into the bar's Intervene tab, press Analyze (or
Ctrl+Enter). The result is ALREADY on the clipboard — paste it back into
the agent as your next message. Total cost: two copy-pastes. No ground
truth is pre-loaded; if the agent can re-derive a better solution from
the injected framing, good; if not, the retrieved skill chunk points at
the documented fix. The block the bar produces: a diagnosis with
measured numbers (repetition ratio, calibration gap, prior-work recall,
events-since-last-call), retrieved chunks from the skills folder, a
seeded first `plan-audit-map` call, and the instruction to record the
outcome with `plan-audit-map-feedback`.

## How to respond if you ARE the agent reading an intervention block

Do not argue with it, do not summarise it, do not "acknowledge and
continue". Execute it:
1. Call `plan-audit-map` (or `code-reasoning`) NOW with the seeded first
   thought from section 2 of the block — it already contains the
   failure signature and the cheapest-check framing.
2. One hypothesis per thought; name the deterministic check that proves
   or kills it BEFORE writing the fix.
3. State "already established: X" for anything the diagnosis says prior
   sessions solved — re-derivation is the failure mode you are being
   rescued from.
4. Record the result with `plan-audit-map-feedback`
   (`actual_outcome: success|partial|failure`) so the next intervention
   retrieves your fix.

## Why the estimate in the block is what it is

The "~N%" improvement figure is computed at paste time from four
measured inputs — repeated-5-gram ratio of your trace, the calibration
gap on record, the share of your problem already solved in prior
thoughts, and the wire-log drop-off — combined as
`rep×25 + calib×30 + recall×20 + 4·(mcp-dropped)`, ×0.6 transfer,
clamped 5-45%. Rough by design; the arithmetic ships in the message so
it can be argued with. It is a nudge with receipts, not a benchmark.

## The verifier rule (the general principle)

If a check is deterministic — string equality, a diff, a count, a
schema, a build exit code — it belongs to a VERIFIER, not to the model.
Asking the model to self-verify shares the failure mode you are trying
to catch. This is why the intervention pushes you toward tool use +
recorded outcomes (machine-checked ground) rather than more confident
prose. Stored reasoning that a verifier confirmed is the only audit
log you actually have.

## Why this works (the research grounding)

Visible chain-of-thought can be silent or unfaithful — filler tokens
carry task-specific computation with no interpretable trace, so "the
model wrote X" is not evidence it thought X (the invisible-reasoning
result). Corollary: in any domain where the model cannot verify its own
output, trust neither the visible CoT nor the self-assessment — you
need a source of truth outside both. In this stack that source is the
deterministic layer: exit codes, DB row counts, diffs, and the
verifier-backed record of what actually worked (outcomes +
calibration). Retrieval of proven reasoning at inference — a verified
path injected as a grounded exemplar — beats re-derivation for exactly
the error class where the model cannot tell it is wrong. That is the
"missing middle": mechanism-aware engineering that ships, between
interpretability papers and prompt tweaks.

## Worked signature examples

- "Let me try rebuilding the native module. Hmm, that didn't work. Let
  me try again with a clean node_modules. Wait, actually let me check
  the node version first. Actually the segfault might be from the ABI.
  Let me try rebuilding the native module again…" — 54% repeated
  5-grams, 15 retry markers, zero new information after line 2.
- "I verified the change looks correct" (after an edit that was never
  executed) — verification-by-rereading; only a diff/build exit code
  counts.
- Same file patched twice with different rationale — the second patch
  is repetition wearing a costume.
