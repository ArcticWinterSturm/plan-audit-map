# Skill: the SQL viewer — tabs, graph, analytics, search, export

## Layout and the three panes

`python3 desk/planauditmap_viewer.py [db-path]` (auto-detects
`~/.plan-audit-map/memory.db`, honours `PLAN_AUDIT_MAP_DB`). Left: session
browser (objective, started, domain, T/R/B counts, confidence, goal;
orphan sessions synthesized from thoughts with no sessions row and
greyed). Middle: thought timeline (monospace listbox + quick filter).
Right: detail notebook (Thought / Metadata / Output / Outcomes / Raw
Row / Context Trace) above a bottom notebook (Branch/Revision Graph,
Analytics, Raw Events). Status bar shows the exact DB path — the first
thing to check when data "is missing" (split-brain DB check).

## Timeline quick filter and navigation

The filter box matches thought text OR thought number and re-renders
the listbox; the counter shows `matched/total`. Selection goes through
a visible-index map (filtered rows point at the right thought — the
original indexed the unfiltered list and showed the WRONG thought after
any search). `Ctrl+Up`/`Ctrl+Down` step thoughts, `Ctrl+F` opens
search, `F5` refreshes everything, double-click a session opens the
export dialog. Switching sessions resets the filter.

## Branch/revision graph

Canvas of numbered nodes: lane 0 is the linear chain, each `branch_id`
gets its own lane; revision edges dashed red (`rev` label), branch
edges blue (branch-id label). Node colors: linear blue, revision red,
branch amber, final (`next_thought_needed` false) green. Zoom
(View menu) rescales spacing/node size; the scroll region grows with
thought count. Clicking a node selects that thought in the timeline.
Malformed thought numbers (non-int or < 1) are skipped, not crashed on.

## Analytics tab

Calibration table: domain × predicted bucket, actual success rate,
sample size, calibration error, last updated — read it as "where the
agent's confidence lies to itself". Patterns table: pattern type +
signature with success/failure counts, success rate, avg confidence.
Stats tab: DB path, totals, table list. Empty here after heavy usage
means nobody is calling plan-audit-map-feedback — the loop that feeds
calibration is opt-in.

## Raw Events tab (the conversation)

Per selected session: every wire event rendered as a transcript turn —
request side (tool + arguments, the `thought` text verbatim) and
response side (unwrapped `result.content[0].text` payload with the
interesting fields: status, session_id, thought_number,
metacognitive_awareness, breakthrough_likelihood, reasoning_mode,
detected_biases, hypothesis_ledger, action_ranking…), plus duration,
client/provider/transport and errors. Sessions without captured events
(none linked) fall back to the 120 newest events across all sessions,
clearly labelled. "(no raw_mcp_events table found)" means the client
bypasses the launcher — see the wire-tap skill.

## Search, bookmarks, export

Search (Ctrl+F): FTS5 `MATCH` with sanitized terms when `thoughts_fts`
exists, LIKE fallback otherwise; results table with snippet + rank;
double-click jumps (selects session, loads thoughts, selects the row).
Bookmarks (Edit menu): stored in `viewer_bookmarks` (the viewer's ONLY
write; needs a writable DB — read-only opens disable with an error on
attempt). Export (double-click a session or File menu): Markdown
(session header + timeline with fenced thought text + outcomes + raw
session JSON), JSON, or JSON with raw events (adds the full
`raw_mcp_events` rows for the session — the "full conversation"
export).

## Reading a session like an auditor

Open the session → scan the Raw Events tab top-to-bottom: it is the
verbatim conversation. Watch for: tool calls whose `duration_ms` spikes
(native rebuilds, cold starts), `isError` responses with validation
text (schema drift — someone sent camelCase), long gaps between the
last `tools/call` and later events (the drop-off that interventions
exist to catch), and `detected_biases` repeating across turns (the
agent anchoring). Then the Timeline: revisions clustered on one number
mean a disputed fact; branches never re-merged mean abandoned
hypotheses. Export "JSON with raw events" hands the whole thing to
whatever analyses you want to run elsewhere.
