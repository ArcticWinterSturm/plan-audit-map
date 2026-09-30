# Skill: one SQLite file, two live writers — WAL in practice

## The situation this stack runs

The Node server (better-sqlite3) and the Python wire tap both hold
`~/.plan-audit-map/memory.db` open and both INSERT, concurrently, forever.
This works — with exactly this recipe: journal_mode=WAL on the database,
`busy_timeout` set by EVERY connection, autocommit-sized writes (one
INSERT/UPDATE, never a transaction held open), and no long readers.
Remove any leg and you get `sqlite3.OperationalError: database is
locked` under load.

## Why WAL

Default rollback-journal mode lets ONE accessor at a time and readers
block writers. WAL (write-ahead logging) flips it: writers append to a
`-wal` file, readers read a consistent snapshot, one writer at a time
with others retrying. Enable once:
`PRAGMA journal_mode = WAL;` — it is persistent in the file. Expect
`memory.db-wal` and `memory.db-shm` siblings; they ARE the database (a
checkpoint folds `-wal` back periodically). Copying only `memory.db`
while a writer is live can silently lose recent commits — use
`sqlite3 src ".backup dst"` or copy all three files after the writer
quiesces.

## The Python side, concretely

```python
conn = sqlite3.connect(path, timeout=10.0, isolation_level=None,
                       check_same_thread=False)
conn.execute("PRAGMA busy_timeout = 8000")
conn.execute("PRAGMA journal_mode = WAL")   # harmless if already WAL
```

- `isolation_level=None` = autocommit: every execute commits
  immediately; no forgotten BEGIN pinning the lock.
- `busy_timeout` (and the connect `timeout`) = retry-on-locked instead
  of instant `OperationalError`. Both the Node and Python writers must
  set it — one rude connection starves the other.
- `check_same_thread=False` is ONLY safe when every access to that
  connection is serialised (one lock). That is the tap's design: pipe
  threads funnel through a single RLock. Without the lock you get
  `SQLite objects created in a thread can only be used in that same
  thread` or silent corruption.

Readers (bar, viewer, intervention engine) should open read-only:
`sqlite3.connect("file:<path>?mode=ro", uri=True, timeout=5.0)` +
`busy_timeout` — zero interference, works while writers are live.

## "database is locked" triage table

| Pattern | Cause | Fix |
|---|---|---|
| Instant error, every time | missing busy_timeout on one side | set it on BOTH writers |
| Under load only | long-held transaction or reader | autocommit writes; no `BEGIN…sleep`; close cursors |
| After a crash | stale `-wal`/`-shm` from a dead process | delete `-wal`/`-shm` only with ALL writers stopped; normally SQLite recovers automatically on next open |
| One writer forever blocked | other process crashed mid-transaction with the lock | restart the dead process; WAL recovers |
| `attempt to write a readonly database` | opened mode=ro then wrote | separate connection for writes |

## Schema creation under concurrency

`CREATE TABLE IF NOT EXISTS` from two processes at first run can race;
wrap it in the same busy_timeout discipline and tolerate failure with
one retry (the tap does exactly this, and also mirrors every event to a
JSONL file so nothing is lost even if the DB is briefly unwritable —
a good pattern for any telemetry side-channel).

## busy_timeout math and checkpointing

`busy_timeout` (ms) is how long SQLite retries a locked write before
raising. Set it longer than your worst writer transaction: here writes
are single-statement (<1 ms), so 8000 ms is enormous headroom — the
point is surviving a slow checkpoint, not normal contention.
Checkpoints (folding `-wal` into the main file) run automatically at
~1000 pages or on last-connection close; a busy reader can delay them,
which is fine — the `-wal` just grows. `PRAGMA wal_checkpoint(TRUNCATE)`
on a quiet connection shrinks a bloated `-wal` after crashes.

## Safe backup recipes

Live DB, writers running: `sqlite3.connect(src).backup(dst_conn)` —
takes a consistent snapshot without stopping anyone. Cold: copy
`memory.db` + `-wal` + `-shm` together after all writers exit. Wrong:
copying only `memory.db` mid-write (silent loss of recent commits), or
using `VACUUM INTO` while a long transaction holds the lock (just
raises busy — retry or use backup()).

## Verifying WAL is actually on

`PRAGMA journal_mode;` returns the current mode — verify `wal` after
setting it once; if it reports `delete`, another connection (or a
read-only opener) reset expectations, and concurrency guarantees are
OFF. This one-line check belongs in any "suddenly locked again"
triage before touching timeouts.
