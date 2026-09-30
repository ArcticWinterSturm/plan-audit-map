# Skill: the activity feed — what the bar shows and where it comes from

## The blended feed

The overview's "Recent activity" tab and the bar's fallback ticker read
`ActivityReader.recent_activity(limit)` — a merge of three sources,
newest first, so the bar is useful even before any wire events exist:

| kind | source table | rendered detail |
|---|---|---|
| `call` | `raw_mcp_events` direction=request | `→ tool` |
| `result` | `raw_mcp_events` ok=1 | `← tool  51ms` |
| `error` | `raw_mcp_events` ok=0 | `✗ tool` |
| `thought` | `thoughts` | `#n/total` (+`rev`/`branch`) |
| `session` | `sessions` | `session start` + objective |

Each row shows time, kind-colored detail, human "ago", short session id
and a text snippet. Tool-call snippets unwrap `request_json` and prefer
the `thought` argument text; thought snippets are the first 240 chars of
`thought`. Ordering is by a timezone-aware timestamp parse of each
row's ts — never raw string compare (the Z-vs-naive trap).

## Poll cycle vs live push

Two update paths: a timer re-reads the DB every `poll_seconds` (3 s
default; WAL readers do not block writers, so this is cheap), and live
`mcp` IPC events from the launcher push tool calls instantly. Live
items win the ticker for ~45 s after the last one (they carry an epoch
and expire), then the DB feed takes over — so the ticker never freezes
on a stale "last tool call" from a dead session. Clicking the bar
forces a `refresh()` immediately.

## The stats line and counts

Header: `{sessions} sessions · {thoughts} thoughts · {events} MCP
events · db {size} MB`. Right end of the strip: `NS TT EE`. LED:
green once any session row exists, dim on an empty DB, green while the
`server` IPC message says up. All-zero counts while a client is
"working" is the bar telling you the pipeline is bypassed (client not
through the launcher) or the server is dead (see the wire-tap and ABI
skills) — the bar is a health monitor, not decoration.

## Empty states mean something specific

- "No activity yet … Watching: <path>" with "(that file does not exist
  yet — created on first use)": the DB path is resolved but nothing has
  ever written it. Start one session through the launcher.
- Activity but zero MCP events: the server writes, the tap does not —
  client bypasses the launcher.
- MCP events but zero thoughts: tap writes, server does not — server
  failing (segfault class) or a different DB path (check the watched
  path in the empty state against the server's env).

## Why "recent" occasionally looks shuffled — and the fix

If a third-party tool sorts the raw tables by their timestamp columns
as strings, UTC `…Z` rows sort before naive local rows for the same
instant (the string compare is zone-blind). The feed avoids this two
ways: SQL orders by `rowid`/`id` (insertion order) and the final merge
sorts by parsed epoch. Any consumer of these tables must do one of the
two — this invariant is documented in the schema skill and is the
single most common regression when people write their own queries
against memory.db.

## Ticker and LED edge cases

- Ticker shows a live event from a session that just ended: it ages out
  in ~45 s; the DB feed takes over with the same information.
- Two clients through two launchers: both stream to the same bar (the
  IPC server accepts multiple connections); events interleave in the
  ticker and `provider`/`client` columns disambiguate them in the DB.
- LED green but counts zero: a sessions row exists but thoughts/events
  do not — someone started a session and never sent a thought; not a
  bar bug.
- db size grows monotonically: WAL + JSONL mirror are append-mostly;
  `PRAGMA wal_checkpoint(TRUNCATE)` and log rotation on the JSONL keep
  them bounded (see the WAL skill).
