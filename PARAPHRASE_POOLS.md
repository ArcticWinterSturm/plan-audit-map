# Paraphrase Pools — plan-audit-map (engineering build)

Copy deck for de-duplicating the user-facing strings in `src/`. Written against the
**current** codebase, not the pre-rewrite tree referenced in `PHRASING_SPEC.md`.
Pool sizes deliberately exceed the spec ("a bit higher"), and the variation budget
is spent aggressively: register, sentence shape, length, and opening move all vary
inside every pool. No two variants anywhere in this document share a three-word
opening.

---

## 1. Status vs `PHRASING_SPEC.md`

| Spec section | Target file | Status |
|---|---|---|
| §1 metacognitive-plugin (13 templates) | `cognitive/plugins/metacognitive-plugin.ts` | **Superseded** — file deleted in the engineering rewrite. Its communicative functions live on: confidence calibration → `verification_gap` metric + recommendations (§H here); assumption questioning → hypothesis-ledger primary actions (§B/§F); perspective shifts → risk-signal guidance (§J). |
| §2 persona-plugin (5 templates) | `cognitive/plugins/persona-plugin.ts` | **Superseded** — file deleted. Synthesis/trade-off framing now lives in `action_ranking` and `ai_recommendations` (§B–§E, §H). Note the `decisionFocus` path in the orchestrator currently never fires: `extractDecisionFocus` is a stub returning `undefined`. Pools for it are included anyway (marked *dead path*) so the code can be re-enabled without new copy. |
| §3.1–3.3 orchestrator actions | `cognitive/cognitive-orchestrator.ts` | Covered — §B, §C, §D, §E, §F, §I |
| §3.4 mode guidance | `cognitive/cognitive-orchestrator.ts` | Covered — §A (25 variants: 5 per mode) |
| §3 (implicit) mode-shift reasons, recommendations | `cognitive/cognitive-orchestrator.ts` | Covered — §G, §H |
| §4 bias-detector | `cognitive/bias-detector.ts` | Covered — §L (pool expansion + selection fix) |
| — (new surface, no spec section) | `cognitive/engineering-profile.ts` | Covered — §J (this module inherited the plugin era's prose role) |
| §1 (insight-detector, listed as "✅ fixed") | `cognitive/insight-detector.ts` | Re-covered — §K (frame templates were single static strings) |

Delivered counts vs spec:

| Surface | Spec asked | Delivered |
|---|---|---|
| Mode guidance (3.4) | 3+/mode (15) | 5/mode (25) |
| Primary action (3.1) | 6+ | 40 actions + 36 rationales across branches |
| Fallback action (3.2) | 6+ | 36 actions + 24 rationales |
| Deferred action (3.3) | 6+ | 36 actions + 24 rationales |
| Default ranking | — | 6 full triples |
| Validation-action wrap | — | 10 |
| Mode-shift reasons | — | 30 (6 × 5 triggers) |
| Recommendations | — | 46 |
| Risk guidance (new) | — | 60 (5 × 12 categories) + 48 label rotations |
| Insight frames | — | 18 |
| Bias strategies (4.1) | 3 | 32 new strategies + 6 frame variants |

---

## 2. Conventions and hard rules

**Dynamic slots** use the real code identifiers, written as `${...}`:

| Slot | Resolves to |
|---|---|
| `${thought_number}` | `thoughtData.thought_number` (int) |
| `${total}` | `thoughtData.total_thoughts` (int) |
| `${remaining}` | `total_thoughts - thought_number` (int) |
| `${history}` | `context.thought_history.length` (int) |
| `${confPct}` | `Math.round(context.confidence_level * 100)` (used as `${confPct}%`) |
| `${complexity}` | `context.complexity` (used as `${complexity}/10`) |
| `${branch_from}` | `thoughtData.branch_from_thought` (int) |
| `${deadline}` | `deadline_hours` (number, hours) |
| `${overlapPct}` | `Math.round(repeatedReasoning.similarity * 100)` (%) |
| `${hypStatus}` | `topHypothesis.status` — categorical, never rewritten |
| `${hypConfPct}` | `Math.round(topHypothesis.confidence * 100)` (%) |
| `${short}` | `topHypothesis.statement` truncated to 50 chars + `…` if longer |
| `${step}` | `topHypothesis.next_validation_step` |
| `${mode}` | current `ReasoningMode` — categorical, never rewritten |
| `${label}` / `${count}` / `${marker}` | risk-signal label, marker count, first matched token |
| `${tradeoff}` | `decisionFocus.tradeoff` (*dead path* today) |
| `${bias}` | `definition.name` — proper noun, never rewritten |
| `${strategy}` | selected debiasing strategy |
| `${primary}` | `actionRanking.primary.action` |

**Rules (supersede/extend spec §5):**

1. **Pluralization:** `(s)` written as `${count === 1 ? '' : 's'}` per existing code style; variants are phrased to read correctly at count 1.
2. **No categorical rewriting.** Mode names, hypothesis statuses, bias names, category `id`s, JSON field names, booleans, and health labels are values, not prose.
3. **No `**Bold Header**` blocks.** Those were plugin-era intervention formats; they died with the plugins. Every surface here is inline prose inside a JSON payload — one or two sentences, no markdown structure, no emoji.
4. **Render-level dynamics (spec §5, kept — applied at the field level, not the line level).**
   Every *rendered* string field must be able to differ across consecutive thoughts.
   Two compliant ways: **(a)** the variant embeds a slot (preferred — 188 of 448 string
   variants carry at least one, and all of §A, §B.1, §F, §H, §K.1), or **(b)**
   the site renders a slot-free variant through a dynamic wrapper — an existing host
   template (§A's `Current reasoning mode: ${mode} - …`) or a context tag from §3.2.
   Never ship a sampled field that could byte-repeat across two different thoughts.
   Injecting a slot into every one of the 500+ variants was rejected on copy-quality grounds:
   `(thought 3)` stapled onto a clean imperative reads like a debug log.
5. **Banned vocabulary** (regression guard for the old build): *metacognitive, persona, vibe, consciousness, energy, mood, resonance*. Words like *confidence* and *evidence* are fine — they name shipped metrics.
6. **Voice:** mechanical, second-person imperative or flat declarative; engineering tools and evidence, never personality. Sentence length across a pool must span terse (≤ 8 words) to full (≤ 28 words) so cross-variant entropy stays high even when slots collide.
7. **Truncation:** spec says 50 chars for statements; code's `summarizeHypothesis` currently cuts at 100. Pick one (recommend 50) and use it for every `${short}`.

---

## §A — `getReasoningModeGuidance` (orchestrator line ~1507)

Rendered inside: `Current reasoning mode: ${mode} - ${guidance}` → lowercase openers, no trailing period.

**5 per mode = 25 (spec asked 15).**

### A.1 `exploration`

1. `map constraints and at least two alternatives before committing — thought ${thought_number} is still wide open`
2. `keep the option tree open; at ${confPct}% confidence a single-track theory is premature`
3. `catalogue the unknowns, the hard constraints, and the rival explanations before anything gets chosen`
4. `widen before you narrow: name what this step has not yet ruled out after ${history} thoughts`
5. `stay in survey mode and defer the verdict; the constraint map matters more than the answer right now`

### A.2 `validation`

1. `put the strongest current claim against one concrete piece of evidence before opening anything new`
2. `pick the load-bearing assertion and run the cheapest check that could break it`
3. `stop expanding the search until the leading claim survives a real test — ${history} thoughts is enough narration`
4. `evidence before breadth: verify whichever claim is carrying the most weight at ${confPct}% confidence`
5. `design the falsifier first — one observation that would sink the current theory — then go get it`

### A.3 `revision`

1. `write down exactly what changed, which evidence killed the prior view, and what replaces it`
2. `log the delta from thought ${thought_number}: old assumption, breaking evidence, replacement under test`
3. `make this belief update auditable — record what moved and why before continuing`
4. `state the correction explicitly so the ledger shows a revision, not a silent drift`
5. `capture before and after: the weakened claim, the trigger, and the new working theory at ${confPct}% confidence`

### A.4 `branching`

1. `define the criterion that decides whether the branch from thought ${branch_from} beats the main path`
2. `run this branch and the incumbent side by side on one shared success metric`
3. `keep the branch honest: pre-commit now to the comparison that will pick a winner`
4. `an unexplored branch is cheap, an uncompared one is useless — set the decision rule before going deeper`
5. `name what this branch must prove relative to the main path, or fold it back after ${history} thoughts`

### A.5 `convergence`

1. `close out: chosen path, supporting evidence, accepted trade-off, next executable step`
2. `compress ${history} thoughts into a decision, its justification, and the first implementation move`
3. `wrap up — name what won, why it won, and what happens next`
4. `consolidate now, in this order: decision, evidence, immediate action`
5. `land the sequence with the conclusion and the next concrete step; only ${remaining} thoughts remain`

---

## §B — `buildPrimaryAction` (orchestrator line ~1138)

Per-branch pools. Actions and rationales mix freely within a branch (rationales are
standalone sentences that follow any action).

### B.1 Branch: `topHypothesis` set — rationale pool (10)

*(Action string comes from `personalizeValidationAction` — see §F.)*

1. `The top hypothesis is ${hypStatus} and still unresolved, so this check buys the most information right now.`
2. `Until "${short}" is settled, every other step inherits its risk — test it first.`
3. `Highest expected information gain sits on the leading claim (${hypStatus}); check it before anything else.`
4. `This is the claim the rest of the plan leans on; confirming or killing it reshapes everything downstream.`
5. `Nothing else outranks an unresolved ${hypStatus} hypothesis sitting at ${hypConfPct}% confidence.`
6. `The cheapest path to certainty runs through the top ledger entry — ${hypStatus} and testable now.`
7. `Settling "${short}" either clears the way or forces a pivot; both outcomes beat more speculation.`
8. `After ${history} thoughts, the leading entry is still ${hypStatus} — one check on it outweighs new exploration.`
9. `One concrete signal on "${short}" does more than three more thoughts of elaboration.`
10. `This check directly prices the biggest open risk: that "${short}" is wrong.`

### B.2 Branch: `decisionFocus` — rationale pool (6) *dead path today*

1. `This primary action is selected to resolve the active trade-off: ${tradeoff}.`
2. `Picked because it is the fastest way to settle ${tradeoff}.`
3. `The open trade-off (${tradeoff}) is the costliest unknown on the table; this move prices it.`
4. `Choosing this step because ${tradeoff} blocks everything behind it.`
5. `This action converts ${tradeoff} from a debate into a decision.`
6. `Resolving ${tradeoff} unlocks the downstream plan; this is the direct route.`

### B.3 Branch: `mode === 'revision'`

Actions (8):

1. `List what changed, what evidence broke the prior view, and the replacement assumption now under test.`
2. `Write the revision as a diff: old claim, killing evidence, new working assumption.`
3. `Name the assumption that just died, the observation that killed it, and what you now believe instead.`
4. `Update the ledger explicitly at thought ${thought_number}: mark the revised entry, cite the contradicting evidence, state the successor claim.`
5. `Document the pivot in one pass — before, after, and the evidence in between.`
6. `Record which earlier thought this revises, why the original weakened, and the test the replacement must pass.`
7. `State the corrected belief and the single observation that forced the correction.`
8. `Summarize the update as before/after, plus the cheapest check of the new assumption.`

Rationales (5):

1. `Revision mode is active, so belief-update quality matters more than adding new scope.`
2. `After ${history} thoughts the ledger only helps if revisions are written, not implied.`
3. `An undocumented revision becomes silent drift; capture it while the evidence is fresh.`
4. `At ${confPct}% confidence mid-revision, the ledger entry is the ground truth worth maintaining.`
5. `New scope can wait — an unaudited belief change cannot.`

### B.4 Branch: `mode === 'branching'`

Actions (8):

1. `Define the decision criterion that will determine whether this branch beats the main path.`
2. `Pick the single metric on which this branch and the incumbent will be compared.`
3. `Declare which dimension this branch must win on — correctness, latency, complexity — before writing more code.`
4. `Pre-register the comparison for the branch from thought ${branch_from}: one shared success metric.`
5. `Write the keep-or-kill rule for this branch before adding depth.`
6. `Decide now what result would send you back to the main path.`
7. `Set the bar: what would this branch have to demonstrate to replace the incumbent?`
8. `Choose the evaluation harness both paths must pass through, then generate this branch's test case.`

Rationales (5):

1. `Branching only helps if the branch can be compared against the incumbent path.`
2. `Undecided criteria turn a branch into open-ended exploration with extra steps.`
3. `The branch from thought ${branch_from} needs a comparison rule before it needs more depth.`
4. `Criteria written up front stop the branch from becoming a sunk cost.`
5. `Deciding the win condition first makes the eventual keep-or-kill call mechanical.`

### B.5 Branch: `mode === 'convergence'` or sequence end

Actions (8):

1. `Summarize the chosen path, the evidence supporting it, and the next executable step.`
2. `Lock the decision: state what won, cite the winning evidence, name the first implementation move.`
3. `Write the verdict and what it produces — decision, justification, next step.`
4. `Close the sequence with the decision, its top two supporting signals, and the accepted trade-off.`
5. `Reduce ${history} thoughts to one decision and one executable action.`
6. `State the conclusion, why the alternatives lost, and what happens in the next hour of work.`
7. `Produce the final output: chosen approach, evidence base, immediate task.`
8. `End with the three deliverables — the decision, the proof, and the next concrete step.`

Rationales (5):

1. `The sequence is already converging, so the best move is to lock in the decision and act.`
2. `With ${remaining} thoughts left, a crisp close beats one more exploration.`
3. `Convergence without a written decision is just stopping; capture the outcome.`
4. `The flag says the sequence is winding down — convert the reasoning into an action now.`
5. `Synthesis is the highest-value step remaining: decision plus executable next move.`

### B.6 Branch: `repeatedReasoning` or `confidence_level < 0.4`

Actions (8):

1. `Run one targeted check that can falsify the current strongest assumption.`
2. `Design the cheapest test that would prove the leading assumption wrong, then run it.`
3. `Stop restating the theory — collect one piece of confirming or disconfirming evidence.`
4. `Identify the assumption doing the most work and probe it with a single concrete experiment.`
5. `Break the loop: take the claim repeated across the last few thoughts and attack it with evidence.`
6. `Find one observation that would force a belief update either way and go get it.`
7. `Swap elaboration for interrogation: one falsifiable check against the strongest claim.`
8. `Choose the load-bearing assumption and hit it with the hardest quick test available.`

Rationales (5):

1. `The reasoning is either looping or low-confidence, so new evidence is more valuable than more elaboration.`
2. `At ${confPct}% confidence, another narrative pass adds nothing; a falsifier would.`
3. `Recent steps overlap by ${overlapPct}% — only a fresh signal can move the state now.`
4. `Repetition means the armchair search is exhausted; the next move must come from the world, not the whiteboard.`
5. `Low confidence plus circular reasoning is the signature of a missing experiment.`

### B.7 Branch: exploration default

Actions (8):

1. `Write down the key constraint and choose one assumption to test next.`
2. `Name the hardest constraint in play, then pick the assumption worth testing first.`
3. `Reduce the map to one narrow, learnable step: a constraint plus a testable assumption.`
4. `List the constraints, rank the assumptions by risk, and commit to testing the riskiest.`
5. `Pick the unknown that most limits the design and plan one probe against it.`
6. `Identify what must be true for any solution to work, then choose how to check it.`
7. `Carve the problem down to a single question that evidence can answer.`
8. `State the binding constraint and nominate the next assumption for a concrete test.`

Rationales (5):

1. `The problem is still in exploration mode and benefits from narrowing to one learnable step.`
2. `Only ${thought_number} thoughts in — map widely, but end each step with a testable pick.`
3. `Exploration pays off only when it terminates in a checkable assumption.`
4. `Breadth now, but aimed: every exploratory step should surface the next test.`
5. `The mode is mapping; the right output is one constraint and one candidate test, not a verdict.`

---

## §C — `buildFallbackAction` (orchestrator line ~1211)

### C.1 Branch: `topHypothesis` set

Actions (6):

1. `Document what evidence would strengthen or reject "${short}".`
2. `Write the validation threshold for "${short}" — what result confirms it, what result kills it.`
3. `Pre-commit: list the observations that would raise or sink the top hypothesis.`
4. `Spell out the pass/fail line for the leading claim before the check becomes possible.`
5. `Record both outcomes — strengthen, reject — and what each would look like in practice.`
6. `Draft the scorecard for "${short}": which signals count for it, which count against.`

Rationales (4):

1. `If the primary check is blocked, the next-best move is to make the validation threshold explicit.`
2. `A blocked test still yields value once its success criteria are written down.`
3. `Explicit thresholds prevent motivated reasoning when the evidence finally lands.`
4. `Writing the bar now keeps the future test honest.`

### C.2 Branch: `decisionFocus` *dead path today*

Actions (6):

1. `Set down the decision rule that will tell you when this trade-off is resolved.`
2. `Define the condition under which ${tradeoff} tips to either side.`
3. `State what measurement would settle ${tradeoff}.`
4. `Record the tipping point: which observation resolves the trade-off.`
5. `Draft the rule that converts ${tradeoff} from an open question into a pending decision.`
6. `Specify the threshold where you stop weighing and start executing.`

Rationales (4):

1. `When the primary action is blocked, make the trade-off explicit and measurable: ${tradeoff}.`
2. `A trade-off with a written resolution rule cannot quietly linger.`
3. `Clarifying the trigger point around ${tradeoff} keeps the decision recoverable.`
4. `Measurable criteria turn an open trade-off into a pending observation.`

### C.3 Branch: `mode === 'convergence'`

Actions (6):

1. `Record the trade-off you are accepting before implementation starts.`
2. `Put in writing the cost you are choosing to pay, and why it is worth paying.`
3. `Note what this decision gives up — explicitly, before building begins.`
4. `Capture the accepted downside so it cannot surprise you later.`
5. `Log the sacrifice: which property loses under the chosen path.`
6. `State the trade-off taken and the condition that would reopen it.`

Rationales (4):

1. `A captured trade-off keeps convergence honest if the chosen path is questioned later.`
2. `Future review needs the accepted downside in writing, not in memory.`
3. `Decisions age better when their costs are itemized up front.`
4. `Recording the trade now prevents retroactive rationalizing.`

### C.4 Branch: `branch_from_thought` set

Actions (6):

1. `Compare this branch against the main path using one shared success metric.`
2. `Run the branch and the incumbent through the same measurement and log both results.`
3. `Score both paths on the single criterion you picked in advance.`
4. `Put the branch head-to-head with the main path on the agreed metric.`
5. `Evaluate branch versus baseline on one axis only — the one that matters most.`
6. `Benchmark the branch against the incumbent before investing further.`

Rationales (4):

1. `A branch without a comparison rule turns into open-ended exploration.`
2. `Side-by-side measurement is the only way a branch earns its keep.`
3. `Without a shared metric, the branch choice becomes taste; force the number.`
4. `Comparisons done late are rationalizations; measure both paths now.`

### C.5 Branch: `complexity >= 8`

Actions (6):

1. `List the main interfaces and failure modes before expanding the solution.`
2. `Map the interface surface and name the two most likely failure modes.`
3. `Sketch the component boundaries and how each one can break.`
4. `Enumerate entry points, integration seams, and their failure paths before building more.`
5. `Draw the blast-radius map: interfaces in, failures out.`
6. `Catalogue the seams and the degraded behavior at each seam.`

Rationales (4):

1. `At complexity ${complexity}/10, structural clarity is the safest fallback move.`
2. `High complexity punishes improvisation; map the seams first.`
3. `With complexity at ${complexity}/10, knowing the failure surface beats adding features.`
4. `Interfaces are where complexity collects — document them before they multiply.`

### C.6 Branch: default

Actions (6):

1. `Capture the current assumption, the missing evidence, and the cheapest next check.`
2. `Write the working assumption, what would disprove it, and the lowest-cost probe.`
3. `Log where things stand: the belief, the gap, and the next affordable experiment.`
4. `Snapshot the state — assumption held, evidence missing, cheapest test queued.`
5. `Record the belief, the hole in the evidence, and the fastest way to fill it.`
6. `Preserve the thread: current position plus the cheapest decisive check.`

Rationales (4):

1. `This preserves momentum even if the preferred action is not immediately possible.`
2. `A written checkpoint keeps ${history} thoughts of progress recoverable.`
3. `Fallback progress is still progress when the next check is priced and queued.`
4. `Momentum survives a blocked primary when the state is on paper.`

---

## §D — `buildDeferredAction` (orchestrator line ~1271)

### D.1 Branch: near deadline (`deadline_hours <= 2`)

Actions (6):

1. `Do not open a new branch or redesign the approach before the next concrete check lands.`
2. `No new branches and no redesigns until the pending check returns a signal.`
3. `Hold the scope exactly where it is until the next experiment reports back.`
4. `Freeze exploration; the remaining ${deadline}h buys verification, not options.`
5. `Resist reopening the design until evidence from the next check arrives.`
6. `Skip any branching or restructuring before the current test resolves.`

Rationales (4):

1. `With ${deadline} hours left, work should reduce uncertainty, not expand the option tree.`
2. `Near-deadline hours buy less pandemonium; new branches spend the little slack that remains.`
3. `Deadline ${deadline}h: every minute spent branching is a minute not spent verifying.`
4. `Under deadline pressure, restraint on scope is the risk control.`

### D.2 Branch: `mode === 'convergence'`

Actions (6):

1. `Do not restart broad exploration unless new contradictory evidence appears.`
2. `No return to wide exploration unless fresh evidence contradicts the decision.`
3. `Stay converged unless something concrete proves the decision wrong.`
4. `Reopen only on new evidence — not on second thoughts.`
5. `Keep the search closed unless a real counterexample shows up.`
6. `Do not drift back into exploration without a falsifying signal.`

Rationales (4):

1. `Convergence is only useful if it resists avoidable thrash.`
2. `Reopening without evidence is anxiety, not analysis.`
3. `A decision that reopens on vibes will close on vibes too.`
4. `Stability after convergence is what makes the earlier search worth anything.`

### D.3 Branch: `repeatedReasoning` or low confidence

Actions (6):

1. `Do not commit to implementation or declare the root cause settled yet.`
2. `Hold off on implementation and on naming a root cause.`
3. `No build-out and no verdict until evidence quality improves.`
4. `Do not freeze the design or call the cause confirmed at ${confPct}% confidence.`
5. `Avoid locking in code or conclusions while the signal stays this weak.`
6. `Postpone commitment — both the coding and the declaring.`

Rationales (4):

1. `Evidence quality at ${confPct}% confidence with ${overlapPct}% thought overlap cannot justify commitment.`
2. `Committing at this confidence converts a guess into a maintenance burden.`
3. `The reasoning has been circling; locking in now bakes the circle into the design.`
4. `Weak signal plus high repetition means today's answer would be tomorrow's revert.`

### D.4 Branch: `decisionFocus` *dead path today*

*(Action comes from `decisionFocus.deferred_action`.)*

Rationales (6):

1. `Avoid collapsing the active trade-off too early: ${tradeoff}.`
2. `Do not let ${tradeoff} resolve by default — resolve it by decision.`
3. `Leave the trade-off open until its trigger fires: ${tradeoff}.`
4. `Premature commitment is how ${tradeoff} gets decided badly.`
5. `Keep both sides of ${tradeoff} alive until the deciding evidence exists.`
6. `Defer the call; trade-offs settled early cost the most to unwind.`

### D.5 Branch: branch active or hypothesis `weakening`

Actions (6):

1. `Do not treat this branch or weakening hypothesis as the chosen answer without a comparison check.`
2. `No commitment to the challenger until it wins a head-to-head with the incumbent.`
3. `Keep the alternative uncommitted until it beats the main path on the agreed metric.`
4. `Do not crown the branch before the comparison runs.`
5. `Hold both paths provisional until one demonstrably wins.`
6. `Wait — an unbenchmarked alternative is an opinion, not an answer.`

Rationales (4):

1. `Alternative paths need explicit validation before they become commitments.`
2. `Switching paths without a comparison trades one guess for another.`
3. `The challenger only earns the seat by beating the incumbent on the record.`
4. `Path changes are expensive; require won evidence, not fresh enthusiasm.`

### D.6 Branch: default

Actions (6):

1. `Do not add more scope until the next action produces a concrete signal.`
2. `No scope growth before the queued check reports in.`
3. `Hold scope constant until new evidence exists.`
4. `Defer every addition until the next signal lands.`
5. `Do not extend the work before the current question gets answered.`
6. `Nothing new enters the plan until the pending test resolves.`

Rationales (4):

1. `Limiting expansion keeps the reasoning grounded and testable.`
2. `Scope added before evidence is scope you cannot evaluate.`
3. `A smaller problem with a real signal beats a bigger one built on fog.`
4. `Growth waits for data; that is what keeps this sequence cheap.`

---

## §E — `buildDefaultActionRanking` (orchestrator line ~1066)

Six complete `primary` / `fallback` / `do_not_do_yet` triples for the degraded path
(`signals: ['fallback']` on all three). Variants 1–3 suit `next_thought_needed: true`;
4–6 suit `false`.

1. — primary: `Pick the strongest remaining assumption and run one concrete check against it.`
   — fallback: `Document the current assumption and the evidence still missing (thought ${thought_number}).`
   — do_not_do_yet: `Do not widen scope or open new branches until one assumption is tested.`
2. — primary: `Choose the claim your plan leans on most and test it with a single observation.`
   — fallback: `Write down the working belief, the gap in its evidence, and the cheapest probe.`
   — do_not_do_yet: `No scope growth while ${remaining} thoughts and zero fresh signals remain.`
3. — primary: `Attack the riskiest open assumption with the cheapest falsifiable check.`
   — fallback: `Record position, missing evidence, and the next affordable experiment.`
   — do_not_do_yet: `Defer every addition until the queued check produces a signal.`
4. — primary: `Summarize the decision, the evidence, and the immediate implementation step.`
   — fallback: `Capture the accepted trade-off and what would reopen it.`
   — do_not_do_yet: `Do not reopen exploration without new contradictory evidence.`
5. — primary: `Close out after ${history} thoughts: chosen path, justification, next action.`
   — fallback: `Log the decision's top two supporting signals before implementing.`
   — do_not_do_yet: `No new branches — the sequence is closing, not reopening.`
6. — primary: `Write the verdict and the first executable step it produces.`
   — fallback: `Note what the decision gives up, in one sentence, before building.`
   — do_not_do_yet: `Resist second-guessing unless a concrete counterexample appears.`

Rationale pool for the degraded path (rotation across all three slots, 4):

1. `Fallback planning is in effect because richer engineering signals were unavailable.`
2. `Signal pipeline is degraded, so a conservative plan is the safe default.`
3. `These steps were generated without full profile data; favor verification over ambition.`
4. `Reduced-context mode: keep every move cheap, concrete, and reversible.`

---

## §F — `personalizeValidationAction` generic wrap (orchestrator line ~1342)

Used when `next_validation_step` is one of the generic steps. `${short}` is the
hypothesis statement truncated to 50 chars. 10 variants:

1. `Test whether "${short}" holds by collecting one concrete confirming or falsifying signal.`
2. `Run the cheapest check that could confirm or break "${short}".`
3. `Uncover one observation that either shores up or sinks "${short}".`
4. `Put "${short}" against a single real measurement.`
5. `Probe "${short}" with the hardest quick test available.`
6. `Collect one decisive data point for or against "${short}".`
7. `Design and run one falsifiable check of "${short}".`
8. `Challenge "${short}" with evidence that would force an update either way.`
9. `Verify or kill "${short}" with one concrete signal — no more narrative.`
10. `Stage the experiment that prices "${short}" in evidence.`

---

## §G — Mode-shift reasons (orchestrator `updateReasoningMode`, ~1448–1498)

Rendered verbatim into `recent_mode_shifts[].reason`. Lowercase, no trailing period.
6 per trigger = 30.

### G.1 Revision (`is_revision`)

1. `thought ${thought_number} explicitly revises an earlier assumption`
2. `thought ${thought_number} marks a stated correction to a prior belief`
3. `an earlier entry was revised at thought ${thought_number}`
4. `thought ${thought_number} rewrote a previous claim in the ledger`
5. `the author flagged thought ${thought_number} as a revision`
6. `belief change recorded at thought ${thought_number}`

### G.2 Branching (`branch_from_thought`)

1. `thought ${thought_number} explores an alternate branch from thought ${branch_from}`
2. `a side path opened at thought ${thought_number}, seeded from thought ${branch_from}`
3. `thought ${thought_number} forks the line started at thought ${branch_from}`
4. `branching declared: thought ${thought_number} diverges from thought ${branch_from}`
5. `thought ${thought_number} pursues a parallel approach to thought ${branch_from}`
6. `an explicit branch was declared at thought ${thought_number}`

### G.3 Near sequence completion

1. `the reasoning sequence is near completion and should consolidate into a decision`
2. `only ${remaining} thoughts remain, so the sequence should close into a decision`
3. `the planned budget is finishing; consolidation mode engaged`
4. `approaching the end of the budget — converge rather than expand`
5. `sequence winding down at thought ${thought_number}: decision and summary take priority`
6. `the remaining budget (${remaining} thoughts) favors closure over exploration`

### G.4 Looping around a hypothesis

1. `recent reasoning is looping around "${short}" and needs a concrete check`
2. `the last steps repeat "${short}" — an external signal is required`
3. `"${short}" keeps recurring without new evidence; test it or drop it`
4. `thoughts are orbiting "${short}"; only a check breaks the orbit`
5. `repetition detected around "${short}" — evidence is the next exit`
6. `this sequence keeps circling "${short}"; a falsifiable probe is due`

### G.5 Exploration default

1. `the current step is still mapping constraints, options, or unknowns`
2. `this step profiles the problem space rather than settling an answer`
3. `constraints and candidates are still being catalogued at thought ${thought_number}`
4. `no commitment yet — the map is still being drawn`
5. `the step surveys the space; nothing is being verified or closed`
6. `breadth-first work is still underway at ${confPct}% confidence`

---

## §H — `generateRecommendations` (orchestrator line ~725)

Pools per push-site. `ai_recommendations` is capped at 5 after dedupe — rotation
keeps the cap from hiding fresh strings across a long session.

### H.1 Top-hypothesis line (6)

1. `Top hypothesis: "${short}" - ${step}`
2. `Leading claim (${hypStatus}): "${short}" — next check: ${step}`
3. `The ledger's top entry is ${hypStatus}: "${short}". Next: ${step}`
4. `Strongest open claim: "${short}". Validate via: ${step}`
5. `"${short}" leads the ledger at ${hypStatus} and ${hypConfPct}%; queued check: ${step}`
6. `Watch "${short}" (${hypStatus}) — the next move is: ${step}`

### H.2 Revision detected (6)

1. `Revision detected - compare the revised assumption against the original and note what changed`
2. `This step revises an earlier one — diff old against new and record the trigger`
3. `A revision is in play at thought ${thought_number}: state the before/after and the evidence that forced it`
4. `Revision flagged; make the change explicit in the ledger instead of implying it`
5. `Compare the revised claim to its predecessor and log the breaking evidence`
6. `Revision is not drift — document old claim, new claim, and cause`

### H.3 Branch active (6)

1. `Branch exploration active - define the decision criteria that will determine whether this branch beats the main path`
2. `A branch is open — pre-commit to the metric that will keep or kill it`
3. `The side path from thought ${branch_from} needs a win condition before more depth`
4. `Set the comparison rule for branch versus main before going further`
5. `Branch active: choose the shared success metric now, at thought ${thought_number}`
6. `Make the branch earn it: define the head-to-head criterion up front`

### H.4 Near deadline (6)

1. `A near deadline is in play - prioritize the next concrete action and defer speculative exploration`
2. `${deadline}h remaining: buy verification, not options`
3. `Deadline pressure — the next concrete check outranks every speculative branch`
4. `With the deadline close, only signal-producing work is affordable`
5. `Compress the plan to the next evidence-producing step; defer the rest`
6. `Near deadline (${deadline}h): cut exploration, keep the check that reduces the most risk`

### H.5 Repeated reasoning (6)

1. `This thought is highly similar to a recent step (${overlapPct}% overlap) - add new evidence, test a different assumption, or converge on a decision`
2. `${overlapPct}% overlap with a prior thought — the next step must import new information`
3. `Looping detected at ${overlapPct}% similarity: seek evidence, change the target, or close`
4. `This step repeats earlier reasoning (${overlapPct}%). Break the loop with a concrete probe.`
5. `Overlap is running at ${overlapPct}% — elaboration has hit diminishing returns`
6. `${overlapPct}% similarity to a recent step: only a fresh signal justifies continuing in ${mode} mode`

### H.6 Near planned end (6)

1. `You are near the planned end of the sequence - converge on a decision or revise total_thoughts explicitly`
2. `One thought left in the budget — close out, or raise total_thoughts on purpose`
3. `Sequence budget nearly spent at thought ${thought_number}: decide, or explicitly extend the plan`
4. `Approaching the planned end; drift is not an option — decide or re-budget`
5. `The plan ends soon: land the decision or formally expand the sequence`
6. `Final stretch (${remaining} remaining) — either converge or consciously revise the total`

### H.7 Primary-action echo (6)

1. `Primary next action: ${primary}`
2. `Next move: ${primary}`
3. `Do this next — ${primary}`
4. `Highest-ranked step: ${primary}`
5. `Queue this first: ${primary}`
6. `The ranked next step is: ${primary}`

### H.8 Empty-fallback pair (`next_thought_needed` true / false, 3 each)

True:

1. `Continue with the next thought by testing the strongest remaining assumption`
2. `Keep going: let the next thought probe the biggest open assumption`
3. `Move forward by attacking the assumption carrying the most weight`

False:

1. `Summarize the decision, supporting evidence, and immediate next action`
2. `End the sequence by stating the decision, its evidence, and the next action`
3. `Wrap up after ${history} thoughts: what was decided, why, and what happens next`

---

## §I — `appendDecisionFocusRationale` suffix (orchestrator ~1390) *dead path today*

Appended after a rationale sentence. 6 variants:

1. `This also resolves the active trade-off: ${tradeoff}.`
2. `It simultaneously settles ${tradeoff}.`
3. `As a bonus, it closes out ${tradeoff}.`
4. `In passing, this decides the open trade-off (${tradeoff}).`
5. `The trade-off ${tradeoff} resolves as a side effect of this step.`
6. `This move doubles as the resolution of ${tradeoff}.`

---

## §J — `RISK_CATEGORIES[].guidance` (engineering-profile.ts)

This module inherited the plugin era's prose role: its strings are the main
engineering voice in `cognitive_insights[].suggested_validation`. Detected markers
are available as `${marker}` (first matched token) and `${count}`. 5 per category = 60.
Variant 1 of each is the current shipped string (canonical; keep or rotate).

### J.1 `correctness`

1. `Point at the exact line, condition, or state transition you believe is wrong, then name the observation that would prove the code is actually correct there.`
2. `Name the input that exposes the "${marker}" failure and the test that would run it; unexecutable suspicions stay open.`
3. `Write the wrongness claim as a failing test case first — line, input, expected, actual.`
4. `For each of the ${count} correctness markers, attach the one observation that settles true-or-false.`
5. `State precisely which line misbehaves and what correct behavior would look like in the debugger before editing.`

### J.2 `regression`

1. `List the concrete callers and code paths this change touches, then state which existing behaviour must be preserved and which test would catch a slip.`
2. `Enumerate every caller of the changed code and write the regression test before the change, not after.`
3. `The word "${marker}" means blast radius; map who calls this and what they assume before touching it.`
4. `Name the existing behavior that must survive and the automated check that proves survival.`
5. `Treat ${count} regression markers as a mandate: caller list first, then a slip-catching test, then the edit.`

### J.3 `verification_gap`

1. `Choose the single claim your next step depends on most and run one concrete check that would falsify it (read the code path, run the query, reproduce the state).`
2. `Take the most load-bearing "${marker}"-class claim and verify it with one real observation before building on it.`
3. `Any claim hedged as "${marker}" is unpriced; pick the most expensive one and run the check that settles it.`
4. `Convert the largest unverified assumption into a pass/fail observation — read the code, run the query, or reproduce the state.`
5. `${count} hedged claims are in play; rank by downside and falsify the worst one first.`

### J.4 `coupling`

1. `Name each module/interface that changes, who depends on it, and what invariant those dependents rely on. If you cannot name a dependent, that is the gap.`
2. `For every interface implicated by "${marker}", list the dependents and the contract they assume; unknown dependents are the risk.`
3. `Write the dependency map before the edit: who calls in, what they assume, what breaks if the assumption dies.`
4. `Treat each "${marker}" mention as a shared-state audit: enumerate owners, readers, and writers.`
5. `If a dependent cannot be named for one of these ${count} coupling markers, finding it is the next action.`

### J.5 `concurrency`

1. `Walk one interleaving by hand: if A completes after B starts but before B finishes, what state do readers observe? Name the ordering guarantee that makes it correct.`
2. `Pick the "${marker}" scenario and trace a single adversarial interleaving line by line, naming the guarantee that saves it.`
3. `State which ordering invariant the code relies on, then construct the schedule that would violate it.`
4. `Hand-simulate the worst plausible timing for one of these ${count} ordering claims and record the observed state.`
5. `No concurrency claim stands without a named guarantee (lock, idempotency, watermark); attach one to each "${marker}" claim.`

### J.6 `data_integrity`

1. `Identify the persisted state involved (rows, statuses, timestamps, keys) and state what happens to existing data when this change ships, including the upgrade path.`
2. `Name the tables, keys, and timestamps implicated by "${marker}", then the fate of pre-existing rows on upgrade day.`
3. `State what existing data experiences during the change: read shape, write shape, and the backfill or migration path.`
4. `For each persistence claim, quote the persisted field and what old values mean after the change ships.`
5. `Upgrade story first: what happens to rows written yesterday when the new code deploys, for each of these ${count} markers.`

### J.7 `failure_modes`

1. `Describe the degraded mode explicitly: what the user observes, what the system retries, and where the operation parks until the dependency returns.`
2. `For the "${marker}" path, write the user-visible symptom, the retry policy, and where work waits during the outage.`
3. `Specify behavior when the dependency is down: timeout, retry, and the resting place of in-flight work.`
4. `Name which of the ${count} failure markers is most likely in production and script its degraded-mode story end to end.`
5. `Every "${marker}" claim needs three answers: what the user sees, what the system retries, where the operation parks.`

### J.8 `security`

1. `Name the trust boundary and the specific input that crosses it, then the exact validation or check that enforces it.`
2. `Identify what crosses the boundary on the "${marker}" path and the single check that stands in front of it.`
3. `Write the abuse case for one of these ${count} security markers: hostile input, crossing point, enforcement line.`
4. `For each "${marker}" claim, quote the validation that rejects bad input — or admit none exists.`
5. `Treat every boundary claim as incomplete until the enforcing check is named by file and function.`

### J.9 `performance`

1. `Quote the operation and its input scale, then the measured or estimated cost. If there is no number attached, treat the claim as unquantified.`
2. `Attach a number to the "${marker}" claim — operation, input size, measured cost — or mark it unquantified.`
3. `Convert performance talk into operation × scale × measured cost; adjectives are not evidence.`
4. `For the strongest of these ${count} cost claims, name the benchmark or query plan that would price it.`
5. `No cost claim ships without an input scale and a measurement; "${marker}" alone is a hypothesis.`

### J.10 `maintainability`

1. `Say what the next change to this code will be, then how the current shape makes that change error-prone. Fix the shape only if it pays for itself in the next change.`
2. `Name the next likely edit; if the "${marker}" shape makes it risky, reshape — otherwise leave the debt documented.`
3. `The "${marker}" claim earns a refactor only if it makes one named, near-term change safer; otherwise it stays a documented known shape.`
4. `Write down which future change this debt taxes and what the tax costs, then fix only if the math wins.`
5. `Take each of the ${count} debt claims and state the concrete change it obstructs; abstract debt is not actionable.`

### J.11 `tradeoff`

1. `For the chosen option, state the trade-off in one sentence: what you accept, and what you are betting will not matter. If you cannot, the analysis is not finished.`
2. `Complete the "${marker}" sentence: accepted downside plus the bet that makes it worth it.`
3. `State what is being given up and the condition that would make the choice wrong.`
4. `A named trade-off without the accepted cost is marketing; write the cost in one sentence.`
5. `Turn each of the ${count} trade-off mentions into: we accept X, betting Y will not matter.`

### J.12 `reversibility`

1. `State how this change is undone in production if it turns out wrong: revert commit, flag flip, data back-migration, or redeploy of the previous artifact.`
2. `Pick the undo mechanism — revert, flag, migration, redeploy — and confirm it actually covers the "${marker}" path.`
3. `Write the rollback story before shipping: which artifact, which data, and how long the undo takes.`
4. `If the "${marker}" claim is wrong, the escape route is ___; fill in the blank with a tested mechanism.`
5. `One of these ${count} reversibility markers must resolve to a concrete undo: commit hash, flag name, or migration script.`

### J.13 Label rotations (4 alternates per category, noun-phrase form)

Display strings only — lookup is by `id`, never by label, so these rotate safely.
Keep a `/` or parenthetical structure so they read correctly inside "…${label}…" frames.

| id | Current label | Alternates |
|---|---|---|
| correctness | correctness claims under pressure | `correctness assertions on the table` · `claims that something is broken` · `defect and edge-case claims` · `right-vs-wrong claims` |
| regression | regression / blast-radius claims | `blast-radius and caller-impact claims` · `backwards-compatibility exposure` · `claims about breaking existing behavior` · `regression risk language` |
| verification_gap | verification gaps (claims not yet checked) | `unchecked claims (hedged or assumed)` · `assertions awaiting verification` · `not-yet-tested claims` · `hedged language that needs a check` |
| coupling | coupling / interface-surface claims | `interface and dependency claims` · `shared-state / contract language` · `coupling surface under discussion` · `module-boundary claims` |
| concurrency | concurrency / ordering claims | `ordering and timing claims` · `interleaving / race language` · `concurrency-surface claims` · `claims about execution order` |
| data_integrity | data-integrity / persistence claims | `persistence and migration claims` · `stored-data risk language` · `schema / row-lifecycle claims` · `durability and upgrade-path claims` |
| failure_modes | failure-mode / degraded-path claims | `degraded-mode and recovery claims` · `error-path language` · `retry / timeout surface claims` · `partial-failure claims` |
| security | security-surface claims | `trust-boundary claims` · `attack-surface language` · `auth / injection exposure claims` · `security-relevant assertions` |
| performance | performance / complexity claims | `cost and scale claims` · `latency / throughput language` · `resource-usage assertions` · `Big-O and bottleneck claims` |
| maintainability | maintainability / debt claims | `tech-debt language` · `shape-of-the-code claims` · `readability / duplication claims` · `debt and refactor talk` |
| tradeoff | trade-offs named explicitly | `explicit cost-acceptance language` · `named trade-offs` · `give-and-get claims` · `downside-acceptance claims` |
| reversibility | reversibility / rollback story | `undo-path language` · `rollback and escape-hatch claims` · `reversibility assertions` · `exit-strategy language` |

---

## §K — `insight-detector.ts` frames

### K.1 `description` frame (10)

Currently: `Risk signal: ${label} (${count} marker(s) in recent reasoning)`.

1. `Risk signal: ${label} (${count} marker${count === 1 ? '' : 's'} in recent reasoning)`
2. `${label} — flagged ${count} time${count === 1 ? '' : 's'} across the current window`
3. `Detected ${count} marker${count === 1 ? '' : 's'} of ${label}`
4. `${count} hit${count === 1 ? '' : 's'} for ${label} within the last ${history} thoughts`
5. `Pattern scan: ${label}, ${count} occurrence${count === 1 ? '' : 's'} in flight`
6. `${count} recent claim${count === 1 ? '' : 's'} fall under ${label}`
7. `Watch item: ${label} — ${count} marker${count === 1 ? '' : 's'} detected`
8. `${label} surfaced ${count} time${count === 1 ? '' : 's'} in the live window`
9. `Lexical scan flags ${label} (${count} marker${count === 1 ? '' : 's'})`
10. `On the radar: ${label}, seen ${count} time${count === 1 ? '' : 's'} up to thought ${thought_number}`

### K.2 `implications` frame (8)

Currently: `Reasoning text contains claims in the "${label}" category — treat them as assertions to check, not facts.`

1. `Reasoning text contains claims in the "${label}" category — treat them as assertions to check, not facts.`
2. `These are statements about ${label}, not evidence of it; require a concrete check before relying on them.`
3. `Claims in this category are unpriced until a real observation backs them.`
4. `Textual markers are not measurements: every claim here needs a named check.`
5. `Treat each claim in this category as a hypothesis pending one concrete signal.`
6. `Mentions of this category flag attention, not confirmation — verify before acting.`
7. `The category fired lexically; the burden of proof stays on the claim.`
8. `Asserted is not demonstrated: hold these claims open until checked.`

---

## §L — `bias-detector.ts` (spec §4)

### L.1 Recommendation frame (6) — line ~589

Currently: `Watch for ${definition.name}: ${definition.debiasing_strategies[0]}`

1. `Watch for ${bias}: ${strategy}`
2. `${bias} risk is live — countermove: ${strategy}`
3. `Possible ${bias}; apply: ${strategy}`
4. `${bias} flagged from the current reasoning — ${strategy}`
5. `Counter ${bias}: ${strategy}`
6. `Flag at thought ${thought_number}: ${bias}. Mitigation — ${strategy}`

### L.2 Strategy pool expansion — `selectDebisingStrategies` (spec §4.1)

**The real §4.1 fix is algorithmic, not copy:** stop taking `slice(0, 2)`. Score each
strategy against the matched `evidence` strings (keyword overlap), weight by that
score, sample without immediate repeat (per-session last-2 exclusion), and return
2–3. The four additions per bias below widen each pool from the shipped entries to
a roster of 6+, so selection has something to choose between.

**Confirmation Bias** (+4):

1. `Run the disconfirming search first: list observations that would prove the current claim false, then go looking for them deliberately.`
2. `Spend one pass arguing the strongest opposing position using only evidence already in the ledger.`
3. `Track confirm-versus-deny counts for the leading hypothesis; a lopsided ledger is the bias made visible at thought ${thought_number}.`
4. `Require every accepted claim to name the test that could have rejected it.`

**Overconfidence Bias** (+4):

1. `Write the confidence as a range with stated error bars, then name what evidence would widen them.`
2. `Ask: if this claim is wrong, what is the earliest cheap signal that would reveal it — at ${confPct}% that signal must exist.`
3. `Compare stated confidence against the verification coverage of the cited claims.`
4. `Force a pre-mortem line — "this failed because ___" — before committing.`

**Anchoring Bias** (+4):

1. `Re-derive the estimate from an independent starting point before comparing it with the first one.`
2. `Delay consulting the initial number until a second approach produces its own figure.`
3. `List what the first suggestion assumed, then test those assumptions directly.`
4. `Generate two alternatives that ignore the anchor, then reconcile all three against the ledger.`

**Availability Heuristic** (+4):

1. `Replace the memorable example with base rates or counts pulled from the actual system.`
2. `Ask which cases never get remembered — near-misses, quiet successes — and price them in.`
3. `Check whether the vivid case is recent, repeated, or merely loud.`
4. `Pull one boring historical counterexample before trusting the vivid one recalled at thought ${thought_number}.`

**Sunk Cost Fallacy** (+4):

1. `Evaluate the plan from today forward; exclude effort already spent from the math.`
2. `Ask: would this path be chosen fresh, with zero history behind it?`
3. `Write the kill criterion for the current approach before any further investment.`
4. `Price the switching cost explicitly instead of letting inertia decide.`

**Framing Effect** (+4):

1. `Restate the choice in the opposite frame — loss versus gain — and check whether the preference flips.`
2. `Strip the adjectives: compare the options on numbers alone.`
3. `Present the same data in two framings and run both through the decision checklist.`
4. `Detect which words are doing the persuasion work and delete them before deciding.`

**Hindsight Bias** (+4):

1. `Record predictions before outcomes wherever possible; score them against the log, not against memory.`
2. `List what was actually knowable at decision time, using the ledger as the source of truth.`
3. `Judge the process by the information available then, not by the outcome known now.`
4. `Note which "obvious" signals were in fact invisible before the outcome landed.`

**Fundamental Attribution Error** (+4):

1. `List the situational constraints — deadline ${deadline}h, load, interfaces — before blaming the actor or component.`
2. `Ask whether the same environment would produce the same behavior in anyone or anything.`
3. `Separate the failure's triggering condition from the unit that exhibited it.`
4. `Test the fix by changing the situation, not the actor.`

---

## 3. Implementation notes

### 3.1 Selection & rotation (extends spec §5)

1. Per pool, keep a per-session ring of the last 2 indices served; resample until the pick is not in the ring. This prevents visible repeats on consecutive thoughts even in small pools (4–6).
2. Prefer weighted sampling: weight = `1 + 0.5 × severity` for pools tied to a risk signal; uniform elsewhere.
3. Seed the RNG in tests (`random(seed)`) so snapshot tests stay deterministic while production varies.
4. **Slot-availability guard:** before sampling, filter the pool to variants whose slots are all defined in context (e.g. skip `${deadline}` variants when `deadline_hours` is undefined, `${overlapPct}` when there is no repeated-reasoning hit, `${branch_from}` when not branching). Never render `undefined`.
5. Pools are plain `readonly string[]` module-level constants next to each function; no external files, no runtime cost — consistent with the cheap-and-targeted constraint.
5. After template substitution, collapse whitespace and trim; keep final strings ≤ 240 chars so JSON payloads stay scan-able.

### 3.2 Context-tag wrappers (the rule-4(b) mechanism)

When a sampled variant carries no slot and the host template adds none, wrap it at
render time with a tag from one of these rotators. Tags are compact, carry their
own slots, and rotate with the same last-2 exclusion as the main pools.

**Trail-offs** (suit rationales, reasons, recommendations — append after the final
period, separated by a space):

1. `(thought ${thought_number}, confidence ${confPct}%)`
2. `(position ${thought_number} of ${total})`
3. `(confidence ${confPct}%, complexity ${complexity}/10)`
4. `(${history} thoughts on record so far)`
5. `(issued at thought ${thought_number}, ${mode} mode)`
6. `(confidence currently ${confPct}% after ${history} thoughts)`

**Lead-ins** (suit imperative actions — prepend, capitalizing the first letter of
the variant after the dash):

1. `Next up (thought ${thought_number}):`
2. `Budget check — ${remaining} thoughts left:`
3. `Looking back over ${history} thoughts:`
4. `Confidence ${confPct}%, complexity ${complexity}/10 —`
5. `In ${mode} mode at thought ${thought_number}:`
6. `Ledger top entry at ${hypConfPct}% —`

Lead-ins 6 and trail-off availability for `${branch_from}` / `${deadline}` variants
are subject to the rule-4 slot-availability guard (§3.1.4).

### 3.3 Uniqueness target (spec §5 acceptance)

Ten consecutive thoughts through the server should show no identical rendered
string in any sampled field. Guarantees combine: pool size (≥ 4 everywhere,
60 in the largest), last-2 exclusion (repeat-free run ≥ pool size − 2), embedded
slots in ~50% of variants, and tag rotation (6 lead-ins × 6 trail-offs = 36 tag
surfaces before repeats are even possible). A 10-thought byte-identical repeat
requires pool size ≤ 3 **and** identical slot values — impossible here, since
`thought_number` increments every render.

### 3.4 Testing

`npm run build`, `npm test`, then a 10-thought stdio session diffing adjacent
payloads per field. Add one unit test per pool asserting (a) rule 4 compliance:
each variant either matches `/\$\{/` or the pool's site is registered as
tag-wrapped per §3.2; and (b) no banned vocabulary (rule 5) in any rendered
output across a fixed-seed 10-thought run.
