# Skill: Re-enter structured reasoning with plan-audit-map (anti-circular CoT)

## When to use
You are mid-task and recognise any of these signals in your own output:
- You have proposed the same fix or check twice with different words.
- You are "verifying" by re-reading your own reasoning instead of running
  something deterministic (a test, a diff, a count, a build).
- Your last several steps contain retry/hedge language ("let me try again",
  "wait, actually", "one more attempt") with no new information gained.
- You stopped calling the plan-audit-map tool and drifted back to native
  chain-of-thought. This is the classic failure: the first half of the
  solution was structured, the second half forgot everything the first half
  learned — including the errors.

If two or more apply: STOP answering from memory. Re-enter the tool.

## The re-entry call
Tool name: `plan-audit-map` (legacy alias `code-reasoning` is accepted).
Arguments are **snake_case** — camelCase is rejected by the schema:

```json
{
  "thought": "Re-entering structured reasoning. Prior verified facts: … .
             Failing approach so far: … . Step 1: <one testable hypothesis>.",
  "thought_number": 1,
  "total_thoughts": 5,
  "next_thought_needed": true
}
```

Rules that make re-entry work:
- One hypothesis per thought. Make it testable and name the cheapest
  deterministic check that proves or kills it BEFORE you write the fix.
- Put the failure signature in the first thought verbatim (error string,
  file, count mismatch). Future retrieval matches on those tokens.
- Never re-derive ground that memory already holds: state "already
  established in prior thought/session: X" instead of re-proving X.
- Use revisions (`is_revision`, `revises_thought`) to correct a numbered
  thought instead of silently changing approach.
- Use branches (`branch_id`, `branch_from_thought`) when you genuinely need
  to explore two hypotheses; do not let branches become a place to hide
  repetition.
- `total_thoughts` is a budget, not a promise: raise it if needed, but if
  you raise it twice without progress, your hypothesis is wrong — say so in
  a thought and pivot.

## Close the loop
After acting on a thought, record what actually happened:

```json
{"tool": "plan-audit-map-feedback",
 "arguments": {"thought_id": "<id>", "actual_outcome": "success" | "partial" | "failure",
               "feedback": "what the deterministic check showed"}}
```

The server turns outcomes into calibration rows and learning patterns, so
every recorded failure makes the NEXT re-entry sharper — an intervention
months later will retrieve your fix, not generic advice.

## Why the estimate in an intervention block is what it is
The intervention message quotes an improvement estimate (e.g. "~14%") built
from measured quantities at that moment: repeated-5-gram ratio of your
circling trace, the calibration gap recorded in memory.db, the share of the
problem already covered by prior thoughts, and wire-log evidence that tool
usage stopped. It is rough (a 0.6 transfer coefficient is applied), but
every input is a real measurement, and the arithmetic is printed in the
message so it can be argued with.
