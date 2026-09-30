/**
 * @fileoverview Paraphrase pools — variant strings for every sampled output field.
 * Each pool is a readonly array. Selection uses last-2 exclusion per session.
 * Slots (${...}) are filled at render time from context.
 */

// ─── §A: getReasoningModeGuidance ──────────────────────────────────────────

export const POOL_EXPLORATION_GUIDANCE = [
  'map constraints and at least two alternatives before committing — thought ${thought_number} is still wide open',
  'keep the option tree open; at ${confPct}% confidence a single-track theory is premature',
  'catalogue the unknowns, the hard constraints, and the rival explanations before anything gets chosen',
  'widen before you narrow: name what this step has not yet ruled out after ${history} thoughts',
  'stay in survey mode and defer the verdict; the constraint map matters more than the answer right now',
] as const;

export const POOL_VALIDATION_GUIDANCE = [
  'put the strongest current claim against one concrete piece of evidence before opening anything new',
  'pick the load-bearing assertion and run the cheapest check that could break it',
  'stop expanding the search until the leading claim survives a real test — ${history} thoughts is enough narration',
  'evidence before breadth: verify whichever claim is carrying the most weight at ${confPct}% confidence',
  'design the falsifier first — one observation that would sink the current theory — then go get it',
] as const;

export const POOL_REVISION_GUIDANCE = [
  'write down exactly what changed, which evidence killed the prior view, and what replaces it',
  'log the delta from thought ${thought_number}: old assumption, breaking evidence, replacement under test',
  'make this belief update auditable — record what moved and why before continuing',
  'state the correction explicitly so the ledger shows a revision, not a silent drift',
  'capture before and after: the weakened claim, the trigger, and the new working theory at ${confPct}% confidence',
] as const;

export const POOL_BRANCHING_GUIDANCE = [
  'define the criterion that decides whether the branch from thought ${branch_from} beats the main path',
  'run this branch and the incumbent side by side on one shared success metric',
  'keep the branch honest: pre-commit now to the comparison that will pick a winner',
  'an unexplored branch is cheap, an uncompared one is useless — set the decision rule before going deeper',
  'name what this branch must prove relative to the main path, or fold it back after ${history} thoughts',
] as const;

export const POOL_CONVERGENCE_GUIDANCE = [
  'close out: chosen path, supporting evidence, accepted trade-off, next executable step',
  'compress ${history} thoughts into a decision, its justification, and the first implementation move',
  'wrap up — name what won, why it won, and what happens next',
  'consolidate now, in this order: decision, evidence, immediate action',
  'land the sequence with the conclusion and the next concrete step; only ${remaining} thoughts remain',
] as const;

// ─── §B: buildPrimaryAction ────────────────────────────────────────────────

export const POOL_TOP_HYPOTHESIS_RATIONALE = [
  'The top hypothesis is ${hypStatus} and still unresolved, so this check buys the most information right now.',
  'Until "${short}" is settled, every other step inherits its risk — test it first.',
  'Highest expected information gain sits on the leading claim (${hypStatus}); check it before anything else.',
  'This is the claim the rest of the plan leans on; confirming or killing it reshapes everything downstream.',
  'Nothing else outranks an unresolved ${hypStatus} hypothesis sitting at ${hypConfPct}% confidence.',
  'The cheapest path to certainty runs through the top ledger entry — ${hypStatus} and testable now.',
  'Settling "${short}" either clears the way or forces a pivot; both outcomes beat more speculation.',
  'After ${history} thoughts, the leading entry is still ${hypStatus} — one check on it outweighs new exploration.',
  'One concrete signal on "${short}" does more than three more thoughts of elaboration.',
  'This check directly prices the biggest open risk: that "${short}" is wrong.',
] as const;

export const POOL_REVISION_ACTIONS = [
  'List what changed, what evidence broke the prior view, and the replacement assumption now under test.',
  'Write the revision as a diff: old claim, killing evidence, new working assumption.',
  'Name the assumption that just died, the observation that killed it, and what you now believe instead.',
  'Update the ledger explicitly at thought ${thought_number}: mark the revised entry, cite the contradicting evidence, state the successor claim.',
  'Document the pivot in one pass — before, after, and the evidence in between.',
  'Record which earlier thought this revises, why the original weakened, and the test the replacement must pass.',
  'State the corrected belief and the single observation that forced the correction.',
  'Summarize the update as before/after, plus the cheapest check of the new assumption.',
] as const;

export const POOL_REVISION_RATIONALES = [
  'Revision mode is active, so belief-update quality matters more than adding new scope.',
  'After ${history} thoughts the ledger only helps if revisions are written, not implied.',
  'An undocumented revision becomes silent drift; capture it while the evidence is fresh.',
  'At ${confPct}% confidence mid-revision, the ledger entry is the ground truth worth maintaining.',
  'New scope can wait — an unaudited belief change cannot.',
] as const;

export const POOL_BRANCHING_ACTIONS = [
  'Define the decision criterion that will determine whether this branch beats the main path.',
  'Pick the single metric on which this branch and the incumbent will be compared.',
  'Declare which dimension this branch must win on — correctness, latency, complexity — before writing more code.',
  'Pre-register the comparison for the branch from thought ${branch_from}: one shared success metric.',
  'Write the keep-or-kill rule for this branch before adding depth.',
  'Decide now what result would send you back to the main path.',
  'Set the bar: what would this branch have to demonstrate to replace the incumbent?',
  'Choose the evaluation harness both paths must pass through, then generate this branch\'s test case.',
] as const;

export const POOL_BRANCHING_RATIONALES = [
  'Branching only helps if the branch can be compared against the incumbent path.',
  'Undecided criteria turn a branch into open-ended exploration with extra steps.',
  'The branch from thought ${branch_from} needs a comparison rule before it needs more depth.',
  'Criteria written up front stop the branch from becoming a sunk cost.',
  'Deciding the win condition first makes the eventual keep-or-kill call mechanical.',
] as const;

export const POOL_CONVERGENCE_ACTIONS = [
  'Summarize the chosen path, the evidence supporting it, and the next executable step.',
  'Lock the decision: state what won, cite the winning evidence, name the first implementation move.',
  'Write the verdict and what it produces — decision, justification, next step.',
  'Close the sequence with the decision, its top two supporting signals, and the accepted trade-off.',
  'Reduce ${history} thoughts to one decision and one executable action.',
  'State the conclusion, why the alternatives lost, and what happens in the next hour of work.',
  'Produce the final output: chosen approach, evidence base, immediate task.',
  'End with the three deliverables — the decision, the proof, and the next concrete step.',
] as const;

export const POOL_CONVERGENCE_RATIONALES = [
  'The sequence is already converging, so the best move is to lock in the decision and act.',
  'With ${remaining} thoughts left, a crisp close beats one more exploration.',
  'Convergence without a written decision is just stopping; capture the outcome.',
  'The flag says the sequence is winding down — convert the reasoning into an action now.',
  'Synthesis is the highest-value step remaining: decision plus executable next move.',
] as const;

export const POOL_LOOP_LOW_CONF_ACTIONS = [
  'Run one targeted check that can falsify the current strongest assumption.',
  'Design the cheapest test that would prove the leading assumption wrong, then run it.',
  'Stop restating the theory — collect one piece of confirming or disconfirming evidence.',
  'Identify the assumption doing the most work and probe it with a single concrete experiment.',
  'Break the loop: take the claim repeated across the last few thoughts and attack it with evidence.',
  'Find one observation that would force a belief update either way and go get it.',
  'Swap elaboration for interrogation: one falsifiable check against the strongest claim.',
  'Choose the load-bearing assumption and hit it with the hardest quick test available.',
] as const;

export const POOL_LOOP_LOW_CONF_RATIONALES = [
  'The reasoning is either looping or low-confidence, so new evidence is more valuable than more elaboration.',
  'At ${confPct}% confidence, another narrative pass adds nothing; a falsifier would.',
  'Recent steps overlap by ${overlapPct}% — only a fresh signal can move the state now.',
  'Repetition means the armchair search is exhausted; the next move must come from the world, not the whiteboard.',
  'Low confidence plus circular reasoning is the signature of a missing experiment.',
] as const;

export const POOL_EXPLORATION_ACTIONS = [
  'Write down the key constraint and choose one assumption to test next.',
  'Name the hardest constraint in play, then pick the assumption worth testing first.',
  'Reduce the map to one narrow, learnable step: a constraint plus a testable assumption.',
  'List the constraints, rank the assumptions by risk, and commit to testing the riskiest.',
  'Pick the unknown that most limits the design and plan one probe against it.',
  'Identify what must be true for any solution to work, then choose how to check it.',
  'Carve the problem down to a single question that evidence can answer.',
  'State the binding constraint and nominate the next assumption for a concrete test.',
] as const;

export const POOL_EXPLORATION_RATIONALES = [
  'The problem is still in exploration mode and benefits from narrowing to one learnable step.',
  'Only ${thought_number} thoughts in — map widely, but end each step with a testable pick.',
  'Exploration pays off only when it terminates in a checkable assumption.',
  'Breadth now, but aimed: every exploratory step should surface the next test.',
  'The mode is mapping; the right output is one constraint and one candidate test, not a verdict.',
] as const;

// ─── §C: buildFallbackAction ───────────────────────────────────────────────

export const POOL_FALLBACK_TOP_HYP_ACTIONS = [
  'Document what evidence would strengthen or reject "${short}".',
  'Write the validation threshold for "${short}" — what result confirms it, what result kills it.',
  'Pre-commit: list the observations that would raise or sink the top hypothesis.',
  'Spell out the pass/fail line for the leading claim before the check becomes possible.',
  'Record both outcomes — strengthen, reject — and what each would look like in practice.',
  'Draft the scorecard for "${short}": which signals count for it, which count against.',
] as const;

export const POOL_FALLBACK_TOP_HYP_RATIONALES = [
  'If the primary check is blocked, the next-best move is to make the validation threshold explicit.',
  'A blocked test still yields value once its success criteria are written down.',
  'Explicit thresholds prevent motivated reasoning when the evidence finally lands.',
  'Writing the bar now keeps the future test honest.',
] as const;

export const POOL_FALLBACK_CONVERGENCE_ACTIONS = [
  'Record the trade-off you are accepting before implementation starts.',
  'Put in writing the cost you are choosing to pay, and why it is worth paying.',
  'Note what this decision gives up — explicitly, before building begins.',
  'Capture the accepted downside so it cannot surprise you later.',
  'Log the sacrifice: which property loses under the chosen path.',
  'State the trade-off taken and the condition that would reopen it.',
] as const;

export const POOL_FALLBACK_CONVERGENCE_RATIONALES = [
  'A captured trade-off keeps convergence honest if the chosen path is questioned later.',
  'Future review needs the accepted downside in writing, not in memory.',
  'Decisions age better when their costs are itemized up front.',
  'Recording the trade now prevents retroactive rationalizing.',
] as const;

export const POOL_FALLBACK_BRANCH_ACTIONS = [
  'Compare this branch against the main path using one shared success metric.',
  'Run the branch and the incumbent through the same measurement and log both results.',
  'Score both paths on the single criterion you picked in advance.',
  'Put the branch head-to-head with the main path on the agreed metric.',
  'Evaluate branch versus baseline on one axis only — the one that matters most.',
  'Benchmark the branch against the incumbent before investing further.',
] as const;

export const POOL_FALLBACK_BRANCH_RATIONALES = [
  'A branch without a comparison rule turns into open-ended exploration.',
  'Side-by-side measurement is the only way a branch earns its keep.',
  'Without a shared metric, the branch choice becomes taste; force the number.',
  'Comparisons done late are rationalizations; measure both paths now.',
] as const;

export const POOL_FALLBACK_COMPLEXITY_ACTIONS = [
  'List the main interfaces and failure modes before expanding the solution.',
  'Map the interface surface and name the two most likely failure modes.',
  'Sketch the component boundaries and how each one can break.',
  'Enumerate entry points, integration seams, and their failure paths before building more.',
  'Draw the blast-radius map: interfaces in, failures out.',
  'Catalogue the seams and the degraded behavior at each seam.',
] as const;

export const POOL_FALLBACK_COMPLEXITY_RATIONALES = [
  'At complexity ${complexity}/10, structural clarity is the safest fallback move.',
  'High complexity punishes improvisation; map the seams first.',
  'With complexity at ${complexity}/10, knowing the failure surface beats adding features.',
  'Interfaces are where complexity collects — document them before they multiply.',
] as const;

export const POOL_FALLBACK_DEFAULT_ACTIONS = [
  'Capture the current assumption, the missing evidence, and the cheapest next check.',
  'Write the working assumption, what would disprove it, and the lowest-cost probe.',
  'Log where things stand: the belief, the gap, and the next affordable experiment.',
  'Snapshot the state — assumption held, evidence missing, cheapest test queued.',
  'Record the belief, the hole in the evidence, and the fastest way to fill it.',
  'Preserve the thread: current position plus the cheapest decisive check.',
] as const;

export const POOL_FALLBACK_DEFAULT_RATIONALES = [
  'This preserves momentum even if the preferred action is not immediately possible.',
  'A written checkpoint keeps ${history} thoughts of progress recoverable.',
  'Fallback progress is still progress when the next check is priced and queued.',
  'Momentum survives a blocked primary when the state is on paper.',
] as const;

// ─── §D: buildDeferredAction ───────────────────────────────────────────────

export const POOL_DEADLINE_ACTIONS = [
  'Do not open a new branch or redesign the approach before the next concrete check lands.',
  'No new branches and no redesigns until the pending check returns a signal.',
  'Hold the scope exactly where it is until the next experiment reports back.',
  'Freeze exploration; the remaining ${deadline}h buys verification, not options.',
  'Resist reopening the design until evidence from the next check arrives.',
  'Skip any branching or restructuring before the current test resolves.',
] as const;

export const POOL_DEADLINE_RATIONALES = [
  'With ${deadline} hours left, work should reduce uncertainty, not expand the option tree.',
  'Near-deadline hours buy less pandemonium; new branches spend the little slack that remains.',
  'Deadline ${deadline}h: every minute spent branching is a minute not spent verifying.',
  'Under deadline pressure, restraint on scope is the risk control.',
] as const;

export const POOL_CONVERGE_DEFER_ACTIONS = [
  'Do not restart broad exploration unless new contradictory evidence appears.',
  'No return to wide exploration unless fresh evidence contradicts the decision.',
  'Stay converged unless something concrete proves the decision wrong.',
  'Reopen only on new evidence — not on second thoughts.',
  'Keep the search closed unless a real counterexample shows up.',
  'Do not drift back into exploration without a falsifying signal.',
] as const;

export const POOL_CONVERGE_DEFER_RATIONALES = [
  'Convergence is only useful if it resists avoidable thrash.',
  'Reopening without evidence is anxiety, not analysis.',
  'A decision that reopens on vibes will close on vibes too.',
  'Stability after convergence is what makes the earlier search worth anything.',
] as const;

export const POOL_WEAK_SIGNAL_DEFER_ACTIONS = [
  'Do not commit to implementation or declare the root cause settled yet.',
  'Hold off on implementation and on naming a root cause.',
  'No build-out and no verdict until evidence quality improves.',
  'Do not freeze the design or call the cause confirmed at ${confPct}% confidence.',
  'Avoid locking in code or conclusions while the signal stays this weak.',
  'Postpone commitment — both the coding and the declaring.',
] as const;

export const POOL_WEAK_SIGNAL_DEFER_RATIONALES = [
  'Evidence quality at ${confPct}% confidence with ${overlapPct}% thought overlap cannot justify commitment.',
  'Committing at this confidence converts a guess into a maintenance burden.',
  'The reasoning has been circling; locking in now bakes the circle into the design.',
  'Weak signal plus high repetition means today\'s answer would be tomorrow\'s revert.',
] as const;

export const POOL_DEFER_BRANCH_ACTIONS = [
  'Do not treat this branch or weakening hypothesis as the chosen answer without a comparison check.',
  'No commitment to the challenger until it wins a head-to-head with the incumbent.',
  'Keep the alternative uncommitted until it beats the main path on the agreed metric.',
  'Do not crown the branch before the comparison runs.',
  'Hold both paths provisional until one demonstrably wins.',
  'Wait — an unbenchmarked alternative is an opinion, not an answer.',
] as const;

export const POOL_DEFER_BRANCH_RATIONALES = [
  'Alternative paths need explicit validation before they become commitments.',
  'Switching paths without a comparison trades one guess for another.',
  'The challenger only earns the seat by beating the incumbent on the record.',
  'Path changes are expensive; require won evidence, not fresh enthusiasm.',
] as const;

export const POOL_DEFER_DEFAULT_ACTIONS = [
  'Do not add more scope until the next action produces a concrete signal.',
  'No scope growth before the queued check reports in.',
  'Hold scope constant until new evidence exists.',
  'Defer every addition until the next signal lands.',
  'Do not extend the work before the current question gets answered.',
  'Nothing new enters the plan until the pending test resolves.',
] as const;

export const POOL_DEFER_DEFAULT_RATIONALES = [
  'Limiting expansion keeps the reasoning grounded and testable.',
  'Scope added before evidence is scope you cannot evaluate.',
  'A smaller problem with a real signal beats a bigger one built on fog.',
  'Growth waits for data; that is what keeps this sequence cheap.',
] as const;

// ─── §E: buildDefaultActionRanking ─────────────────────────────────────────

export const POOL_DEFAULT_RANKINGS = [
  {
    primary: 'Pick the strongest remaining assumption and run one concrete check against it.',
    fallback: 'Document the current assumption and the evidence still missing (thought ${thought_number}).',
    do_not_do_yet: 'Do not widen scope or open new branches until one assumption is tested.',
  },
  {
    primary: 'Choose the claim your plan leans on most and test it with a single observation.',
    fallback: 'Write down the working belief, the gap in its evidence, and the cheapest probe.',
    do_not_do_yet: 'No scope growth while ${remaining} thoughts and zero fresh signals remain.',
  },
  {
    primary: 'Attack the riskiest open assumption with the cheapest falsifiable check.',
    fallback: 'Record position, missing evidence, and the next affordable experiment.',
    do_not_do_yet: 'Defer every addition until the queued check produces a signal.',
  },
  {
    primary: 'Summarize the decision, the evidence, and the immediate implementation step.',
    fallback: 'Capture the accepted trade-off and what would reopen it.',
    do_not_do_yet: 'Do not reopen exploration without new contradictory evidence.',
  },
  {
    primary: 'Close out after ${history} thoughts: chosen path, justification, next action.',
    fallback: 'Log the decision\'s top two supporting signals before implementing.',
    do_not_do_yet: 'No new branches — the sequence is closing, not reopening.',
  },
  {
    primary: 'Write the verdict and the first executable step it produces.',
    fallback: 'Note what the decision gives up, in one sentence, before building.',
    do_not_do_yet: 'Resist second-guessing unless a concrete counterexample appears.',
  },
] as const;

export const POOL_DEFAULT_RANKING_RATIONALES = [
  'Fallback planning is in effect because richer engineering signals were unavailable.',
  'Signal pipeline is degraded, so a conservative plan is the safe default.',
  'These steps were generated without full profile data; favor verification over ambition.',
  'Reduced-context mode: keep every move cheap, concrete, and reversible.',
] as const;

// ─── §F: personalizeValidationAction ───────────────────────────────────────

export const POOL_VALIDATION_ACTIONS = [
  'Test whether "${short}" holds by collecting one concrete confirming or falsifying signal.',
  'Run the cheapest check that could confirm or break "${short}".',
  'Uncover one observation that either shores up or sinks "${short}".',
  'Put "${short}" against a single real measurement.',
  'Probe "${short}" with the hardest quick test available.',
  'Collect one decisive data point for or against "${short}".',
  'Design and run one falsifiable check of "${short}".',
  'Challenge "${short}" with evidence that would force an update either way.',
  'Verify or kill "${short}" with one concrete signal — no more narrative.',
  'Stage the experiment that prices "${short}" in evidence.',
] as const;

// ─── §G: Mode-shift reasons ────────────────────────────────────────────────

export const POOL_MODE_SHIFT_REVISION = [
  'thought ${thought_number} explicitly revises an earlier assumption',
  'thought ${thought_number} marks a stated correction to a prior belief',
  'an earlier entry was revised at thought ${thought_number}',
  'thought ${thought_number} rewrote a previous claim in the ledger',
  'the author flagged thought ${thought_number} as a revision',
  'belief change recorded at thought ${thought_number}',
] as const;

export const POOL_MODE_SHIFT_BRANCHING = [
  'thought ${thought_number} explores an alternate branch from thought ${branch_from}',
  'a side path opened at thought ${thought_number}, seeded from thought ${branch_from}',
  'thought ${thought_number} forks the line started at thought ${branch_from}',
  'branching declared: thought ${thought_number} diverges from thought ${branch_from}',
  'thought ${thought_number} pursues a parallel approach to thought ${branch_from}',
  'an explicit branch was declared at thought ${thought_number}',
] as const;

export const POOL_MODE_SHIFT_NEAR_END = [
  'the reasoning sequence is near completion and should consolidate into a decision',
  'only ${remaining} thoughts remain, so the sequence should close into a decision',
  'the planned budget is finishing; consolidation mode engaged',
  'approaching the end of the budget — converge rather than expand',
  'sequence winding down at thought ${thought_number}: decision and summary take priority',
  'the remaining budget (${remaining} thoughts) favors closure over exploration',
] as const;

export const POOL_MODE_SHIFT_LOOPING = [
  'recent reasoning is looping around "${short}" and needs a concrete check',
  'the last steps repeat "${short}" — an external signal is required',
  '"${short}" keeps recurring without new evidence; test it or drop it',
  'thoughts are orbiting "${short}"; only a check breaks the orbit',
  'repetition detected around "${short}" — evidence is the next exit',
  'this sequence keeps circling "${short}"; a falsifiable probe is due',
] as const;

export const POOL_MODE_SHIFT_EXPLORATION = [
  'the current step is still mapping constraints, options, or unknowns',
  'this step profiles the problem space rather than settling an answer',
  'constraints and candidates are still being catalogued at thought ${thought_number}',
  'no commitment yet — the map is still being drawn',
  'the step surveys the space; nothing is being verified or closed',
  'breadth-first work is still underway at ${confPct}% confidence',
] as const;

// ─── §H: generateRecommendations ───────────────────────────────────────────

export const POOL_REC_TOP_HYPOTHESIS = [
  'Top hypothesis: "${short}" — ${step}',
  'Leading claim (${hypStatus}): "${short}" — next check: ${step}',
  'The ledger\'s top entry is ${hypStatus}: "${short}". Next: ${step}',
  'Strongest open claim: "${short}". Validate via: ${step}',
  '"${short}" leads the ledger at ${hypStatus} and ${hypConfPct}%; queued check: ${step}',
  'Watch "${short}" (${hypStatus}) — the next move is: ${step}',
] as const;

export const POOL_REC_REVISION = [
  'Revision detected — compare the revised assumption against the original and note what changed',
  'This step revises an earlier one — diff old against new and record the trigger',
  'A revision is in play at thought ${thought_number}: state the before/after and the evidence that forced it',
  'Revision flagged; make the change explicit in the ledger instead of implying it',
  'Compare the revised claim to its predecessor and log the breaking evidence',
  'Revision is not drift — document old claim, new claim, and cause',
] as const;

export const POOL_REC_BRANCH = [
  'Branch exploration active — define the decision criteria that will determine whether this branch beats the main path',
  'A branch is open — pre-commit to the metric that will keep or kill it',
  'The side path from thought ${branch_from} needs a win condition before more depth',
  'Set the comparison rule for branch versus main before going further',
  'Branch active: choose the shared success metric now, at thought ${thought_number}',
  'Make the branch earn it: define the head-to-head criterion up front',
] as const;

export const POOL_REC_DEADLINE = [
  'A near deadline is in play — prioritize the next concrete action and defer speculative exploration',
  '${deadline}h remaining: buy verification, not options',
  'Deadline pressure — the next concrete check outranks every speculative branch',
  'With the deadline close, only signal-producing work is affordable',
  'Compress the plan to the next evidence-producing step; defer the rest',
  'Near deadline (${deadline}h): cut exploration, keep the check that reduces the most risk',
] as const;

export const POOL_REC_REPEATED = [
  'This thought is highly similar to a recent step (${overlapPct}% overlap) — add new evidence, test a different assumption, or converge on a decision',
  '${overlapPct}% overlap with a prior thought — the next step must import new information',
  'Looping detected at ${overlapPct}% similarity: seek evidence, change the target, or close',
  'This step repeats earlier reasoning (${overlapPct}%). Break the loop with a concrete probe.',
  'Overlap is running at ${overlapPct}% — elaboration has hit diminishing returns',
  '${overlapPct}% similarity to a recent step: only a fresh signal justifies continuing in ${mode} mode',
] as const;

export const POOL_REC_NEAR_END = [
  'You are near the planned end of the sequence — converge on a decision or revise total_thoughts explicitly',
  'One thought left in the budget — close out, or raise total_thoughts on purpose',
  'Sequence budget nearly spent at thought ${thought_number}: decide, or explicitly extend the plan',
  'Approaching the planned end; drift is not an option — decide or re-budget',
  'The plan ends soon: land the decision or formally expand the sequence',
  'Final stretch (${remaining} remaining) — either converge or consciously revise the total',
] as const;

export const POOL_REC_PRIMARY_ACTION = [
  'Primary next action: ${primary}',
  'Next move: ${primary}',
  'Do this next — ${primary}',
  'Highest-ranked step: ${primary}',
  'Queue this first: ${primary}',
  'The ranked next step is: ${primary}',
] as const;

export const POOL_REC_EMPTY_TRUE = [
  'Continue with the next thought by testing the strongest remaining assumption',
  'Keep going: let the next thought probe the biggest open assumption',
  'Move forward by attacking the assumption carrying the most weight',
] as const;

export const POOL_REC_EMPTY_FALSE = [
  'Summarize the decision, supporting evidence, and immediate next action',
  'End the sequence by stating the decision, its evidence, and the next action',
  'Wrap up after ${history} thoughts: what was decided, why, and what happens next',
] as const;

// ─── §I: appendDecisionFocusRationale ──────────────────────────────────────

export const POOL_DECISION_FOCUS_RATIONALE = [
  'This also resolves the active trade-off: ${tradeoff}.',
  'It simultaneously settles ${tradeoff}.',
  'As a bonus, it closes out ${tradeoff}.',
  'In passing, this decides the open trade-off (${tradeoff}).',
  'The trade-off ${tradeoff} resolves as a side effect of this step.',
  'This move doubles as the resolution of ${tradeoff}.',
] as const;

// ─── §K: insight-detector frames ───────────────────────────────────────────

export const POOL_INSIGHT_DESCRIPTION = [
  'Risk signal: ${label} (${count} marker${count === 1 ? \'\' : \'s\'} in recent reasoning)',
  '${label} — flagged ${count} time${count === 1 ? \'\' : \'s\'} across the current window',
  'Detected ${count} marker${count === 1 ? \'\' : \'s\'} of ${label}',
  '${count} hit${count === 1 ? \'\' : \'s\'} for ${label} within the last ${history} thoughts',
  'Pattern scan: ${label}, ${count} occurrence${count === 1 ? \'\' : \'s\'} in flight',
  '${count} recent claim${count === 1 ? \'\' : \'s\'} fall under ${label}',
  'Watch item: ${label} — ${count} marker${count === 1 ? \'\' : \'s\'} detected',
  '${label} surfaced ${count} time${count === 1 ? \'\' : \'s\'} in the live window',
  'Lexical scan flags ${label} (${count} marker${count === 1 ? \'\' : \'s\'})',
  'On the radar: ${label}, seen ${count} time${count === 1 ? \'\' : \'s\'} up to thought ${thought_number}',
] as const;

export const POOL_INSIGHT_IMPLICATIONS = [
  'Reasoning text contains claims in the "${label}" category — treat them as assertions to check, not facts.',
  'These are statements about ${label}, not evidence of it; require a concrete check before relying on them.',
  'Claims in this category are unpriced until a real observation backs them.',
  'Textual markers are not measurements: every claim here needs a named check.',
  'Treat each claim in this category as a hypothesis pending one concrete signal.',
  'Mentions of this category flag attention, not confirmation — verify before acting.',
  'The category fired lexically; the burden of proof stays on the claim.',
  'Asserted is not demonstrated: hold these claims open until checked.',
] as const;

// ─── §L: bias-detector strategy expansion ──────────────────────────────────

export const POOL_BIAS_RECOMMENDATION_FRAMES = [
  'Watch for ${bias}: ${strategy}',
  '${bias} risk is live — countermove: ${strategy}',
  'Possible ${bias}; apply: ${strategy}',
  '${bias} flagged from the current reasoning — ${strategy}',
  'Counter ${bias}: ${strategy}',
  'Flag at thought ${thought_number}: ${bias}. Mitigation — ${strategy}',
] as const;

export const POOL_CONFIRMATION_STRATEGIES = [
  'Actively seek contradicting evidence',
  'Ask: "What would change my mind?"',
  'Consider alternative hypotheses with equal weight',
  'Seek input from someone with an opposing view',
  'Run the disconfirming search first: list observations that would prove the current claim false, then go looking for them deliberately.',
  'Spend one pass arguing the strongest opposing position using only evidence already in the ledger.',
  'Track confirm-versus-deny counts for the leading hypothesis; a lopsided ledger is the bias made visible at thought ${thought_number}.',
  'Require every accepted claim to name the test that could have rejected it.',
] as const;

export const POOL_OVERCONFIDENCE_STRATEGIES = [
  'Assign probability ranges instead of point estimates',
  'Track prediction accuracy over time',
  'Consider base rates for similar situations',
  'Ask: "What don\'t I know?"',
  'Write the confidence as a range with stated error bars, then name what evidence would widen them.',
  'Ask: if this claim is wrong, what is the earliest cheap signal that would reveal it — at ${confPct}% that signal must exist.',
  'Compare stated confidence against the verification coverage of the cited claims.',
  'Force a pre-mortem line — "this failed because ___" — before committing.',
] as const;

export const POOL_ANCHORING_STRATEGIES = [
  'Generate estimates before seeing reference points',
  'Consider multiple anchor points',
  'Ask: "Would I think differently if I started elsewhere?"',
  'Use structured analytical techniques',
  'Re-derive the estimate from an independent starting point before comparing it with the first one.',
  'Delay consulting the initial number until a second approach produces its own figure.',
  'List what the first suggestion assumed, then test those assumptions directly.',
  'Generate two alternatives that ignore the anchor, then reconcile all three against the ledger.',
] as const;

export const POOL_AVAILABILITY_STRATEGIES = [
  'Seek out systematic data, not just examples',
  'Ask: "What might I be missing due to its low salience?"',
  'Consider base rates from reliable sources',
  'Be aware of media bias in what gets covered',
  'Replace the memorable example with base rates or counts pulled from the actual system.',
  'Ask which cases never get remembered — near-misses, quiet successes — and price them in.',
  'Check whether the vivid case is recent, repeated, or merely loud.',
  'Pull one boring historical counterexample before trusting the vivid one recalled at thought ${thought_number}.',
] as const;

export const POOL_SUNK_COST_STRATEGIES = [
  'Evaluate decisions based on future value only',
  'Ask: "Would I make this choice if starting fresh?"',
  'Consider opportunity costs of continuing',
  'Set clear exit criteria before starting',
  'Evaluate the plan from today forward; exclude effort already spent from the math.',
  'Ask: would this path be chosen fresh, with zero history behind it?',
  'Write the kill criterion for the current approach before any further investment.',
  'Price the switching cost explicitly instead of letting inertia decide.',
] as const;

export const POOL_FRAMING_STRATEGIES = [
  'Reframe the problem in multiple ways',
  'Consider both gains and losses explicitly',
  'Use absolute numbers alongside percentages',
  'Ask: "How would I see this if framed differently?"',
  'Restate the choice in the opposite frame — loss versus gain — and check whether the preference flips.',
  'Strip the adjectives: compare the options on numbers alone.',
  'Present the same data in two framings and run both through the decision checklist.',
  'Detect which words are doing the persuasion work and delete them before deciding.',
] as const;

export const POOL_HINDSIGHT_STRATEGIES = [
  'Document predictions before outcomes are known',
  'Consider alternative outcomes that could have occurred',
  'Remember the uncertainty that existed at decision time',
  'Focus on decision quality, not outcome quality',
  'Record predictions before outcomes wherever possible; score them against the log, not against memory.',
  'List what was actually knowable at decision time, using the ledger as the source of truth.',
  'Judge the process by the information available then, not by the outcome known now.',
  'Note which "obvious" signals were in fact invisible before the outcome landed.',
] as const;

export const POOL_ATTRIBUTION_STRATEGIES = [
  'Consider situational factors before attributing to character',
  'Ask: "What circumstances might explain this behavior?"',
  'Imagine how you might act in the same situation',
  'Look for multiple causes of behavior',
  'List the situational constraints — deadline ${deadline}h, load, interfaces — before blaming the actor or component.',
  'Ask whether the same environment would produce the same behavior in anyone or anything.',
  'Separate the failure\'s triggering condition from the unit that exhibited it.',
  'Test the fix by changing the situation, not the actor.',
] as const;
