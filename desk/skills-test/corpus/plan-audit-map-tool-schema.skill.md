# Skill: the plan-audit-map tool — exact schema, metrics, feedback loop

## Tool names and the snake_case rule

The tool is `plan-audit-map`; the legacy alias `code-reasoning` is still
accepted for old clients. Arguments are STRICT snake_case. camelCase is
rejected by the zod schema with:
`Validation errors found: Unrecognized key(s) in object: 'thoughtNumber'`
— if you send `thoughtNumber`/`totalThoughts`/`nextThoughtNeeded` the
call fails with `isError: true` and that exact message. Core arguments:
`thought` (string, max length 20000), `thought_number` (int ≥ 1),
`total_thoughts` (int), `next_thought_needed` (bool). The server
generates its own `session_<uuid>` — a client-supplied `session_id`
argument is REJECTED (`Unrecognized key(s) in object: 'session_id'`);
the id comes back in the response payload. Revision/branch fields when
needed: `is_revision` + `revises_thought`, `branch_id` +
`branch_from_thought`.

## Reading the response

`result.content[0].text` is a JSON string; parse it. Keys you will see:
`status`, `session_id`, `thought_number`, `total_thoughts`,
`next_thought_needed`, `thought_history_length`, `branches`, and the
cognitive block:

| Key | Meaning |
|---|---|
| `cognitive_state` / `reasoning_mode` | current mode classification (e.g. analytical) |
| `metacognitive_awareness` | 0-1 self-monitoring score |
| `breakthrough_likelihood` | 0-1 estimate a breakthrough is near |
| `creative_pressure` | 0-1 divergence pressure |
| `cognitive_flexibility` | 0-1 ability to switch approaches |
| `insight_potential` | 0-1 |
| `detected_biases` | list, e.g. anchoring |
| `hypothesis_ledger` | tracked hypotheses |
| `action_ranking`, `ai_recommendations`, `cognitive_interventions`, `cognitive_insights`, `recent_mode_shifts`, `recommended_external_tools` | advisory lists |

Server-side bounds worth knowing: the in-memory thought ring is capped
at 20 thoughts (MAX_THOUGHTS); bias detection sees the most recent 5
thoughts (MAX_PREVIOUS_THOUGHTS_CONTEXT); thoughts longer than 20000
chars are rejected.

## Using it like the designer intended

One hypothesis per thought. Before writing a fix, name the cheapest
DETERMINISTIC check that proves or kills the hypothesis (a test, a
diff, a count, a build) — never "verify" by re-reading your own
reasoning. Never re-derive solved ground: write "already established in
prior thought/session: X" and move on. Use `is_revision` to correct a
numbered thought instead of silently changing approach. Use
`branch_id`/`branch_from_thought` for genuine alternative hypotheses,
not as a hiding place for repetition. `total_thoughts` is a budget, not
a promise: raising it twice with no progress means the hypothesis is
wrong — say so in a thought and pivot.

## Closing the loop: plan-audit-map-feedback

After acting on a thought, record what ACTUALLY happened:

```json
{"tool": "plan-audit-map-feedback",
 "arguments": {"thought_id": "<id>", "actual_outcome": "success|partial|failure",
               "feedback": "what the deterministic check showed"}}
```

Outcomes land in the `outcomes` table and feed `confidence_calibration`
(per-domain predicted vs actual success rates) and `learning_patterns`.
This is what makes later interventions retrieve YOUR fix instead of
generic advice — the intervention engine's estimate literally reads the
calibration gap you accumulated here, and prior-work matching searches
`thoughts` rows for the failure signature tokens you wrote down.

## Prompts capability

The server exposes 5 built-in prompts via the MCP prompts capability and
loads custom ones from `~/.plan-audit-map/prompts/*.md`
(`prompt_values.json` stores values). With `--no-dashboard` or prompts
disabled the capability is omitted from `initialize` — clients list
fewer features, which is not an error.

## Worked call and response (real shapes)

Request:
```json
{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"plan-audit-map",
 "arguments":{"thought":"The segfault is ABI: better-sqlite3@13 on node 20.
 Check with npm ls better-sqlite3.","thought_number":1,"total_thoughts":3,
 "next_thought_needed":true}}}
```
Response `result.content[0].text` (parse it): `{"status":"processed",
"session_id":"session_61098e3e-…","thought_number":1,"total_thoughts":3,
"next_thought_needed":true,"thought_history_length":1,"cognitive_state":{…},
"reasoning_mode":"analytical","metacognitive_awareness":0.62,
"breakthrough_likelihood":0.28,"detected_biases":["anchoring"],…}`.
Failure of validation arrives as a normal response with `isError: true`
and the "Validation errors found: Unrecognized key(s)…" text — handle
it, do not retry the same shape.

## Feedback → calibration flow

plan-audit-map-feedback writes an `outcomes` row; the server then updates
`confidence_calibration` (predicted confidence bucket vs actual
success rate per domain, sample-size weighted) and `learning_patterns`
(success/failure counts per pattern signature). Downstream consumers:
the viewer's Analytics tab (calibration + patterns tables), the
intervention estimate (reads the weighted gap), and future you — this
table IS the mechanism by which the system learns your failure modes
without any model retraining.
