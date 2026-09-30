# Skill: the intervention paste bar — engine reference and tuning

## What it is (the missing middle, shipped)

Models do plan-audit-map for the first stretch of a solution, then silently
drop back to native chain-of-thought uninformed by prior errors and start
circling. The paste bar is the manual lever: a human pastes the agent's
last few messages, and gets back ONE copy-paste block — the whole
intervention costs two C+V round trips and pre-loads zero ground-truth
tokens. The block contains, in priority order: diagnosis with measured
numbers, retrieved skill chunks, a seeded first `plan-audit-map` call, and
the instruction to record outcomes with `plan-audit-map-feedback` so the
NEXT intervention retrieves this agent's own fix. Entry points: the
overview's Intervene tab, the "🛟 Intervene" strip segment, the
right-click menu, IPC `{"type":"intervene"}`, or
`planauditmap_launcher.py --open-intervention` (starts the bar if needed).

## Embedding provider ladder (config under `intervention`)

`embedding_provider` = auto | ollama | lmstudio | nomic | local. Auto
tries, in order: Ollama at `127.0.0.1:11434` (alive check `GET
/api/tags`), LM Studio at `127.0.0.1:1234` (alive check `GET
/v1/models`), then falls back to the deterministic offline hashed
n-gram embedder. If the endpoint is not the default, set
`embedding_endpoint`. Ollama embeddings: `POST /api/embed` with
`{"model","input":[…]}` (batch, Ollama ≥ 0.2.6) with fallback to legacy
`POST /api/embeddings` per prompt. LM Studio: OpenAI-compatible `POST
/v1/embeddings`. `nomic` = api.nomic.ai cloud, requires `NOMIC_API_KEY`
(only when explicitly configured — it costs money). Model default:
`nomic-embed-text` (`ollama pull nomic-embed-text`).

"offline fallback (no server found)" while Ollama runs usually means the
endpoint/model name in `intervention` does not match what the server
actually serves — check `ollama list` and the `embedding_endpoint` value;
the alive check must pass BEFORE any embed call is attempted.

## Retrieval: hybrid score, not pure cosine

`score = 0.65 × embedding_cosine + 0.35 × lexical_overlap` where lexical
overlap = |top-15 salient paste tokens ∩ chunk tokens| / 15. Rationale:
with the offline hashed embedder (or any weak embedder) pure cosine is
bag-of-words anyway; the lexical term guarantees that a paste quoting
"sqlite segfault node 20" lands on the chunk that literally contains
those tokens. `top_k` chunks above `min_score` (default 3 / 0.04) are
retrieved. Skills are chunked at `##`/`###` headings, windowed at
`max_chunk_chars` 1400 with one-paragraph overlap; `README*` files are
skipped by the indexer.

## The index cache

`~/.plan-audit-map/skills-index.json` stores per-file chunks + vectors,
keyed by file mtime+size; unchanged files are never re-embedded (second
analysis ~5 ms). Cache is invalidated wholesale when the embedding
provider changes (`provider` field) or the format version bumps. If
retrieval seems stale after swapping skills folders, delete the cache
file once.

## The improvement estimate — every input measured

`estimate = clamp(round(0.6 × (rep_gain + calib_gain + recall_gain +
drop_bonus)), 5, 45)` percent, where:
- `rep_gain = rep5_ratio × 25` — repeated-5-gram ratio of the pasted
  trace (share of 5-gram positions occurring more than once)
- `calib_gain = calibration_gap × 30` — weighted mean of
  `|predicted_bucket − actual_success_rate|` over the server's
  `confidence_calibration` rows (sample-size weighted when populated,
  row-average fallback)
- `recall_gain = recall × 20` — share of the paste's top salient tokens
  found in prior `thoughts` rows (already-solved ground)
- `drop_bonus = 4` flat when the wire log shows ≥ 10 events since the
  last `tools/call` (the "forgot the MCP" signature)
- `0.6` transfer coefficient: not all recovered effort converts to
  performance.

The full arithmetic is printed in the message
(`work: repetition 0.54→+13.6; calibration gap 0.10 (n=57)→+3.0; …`)
so the number can be argued with. It is a rough estimate by design; it
is never a placeholder. Other measured diagnostics included: longest
repeated token block, retry/hedge marker count, prior matched
thoughts/sessions, best prior session goal/confidence, last recorded
cognitive state (reasoning_mode, metacognitive_awareness,
breakthrough_likelihood) from the newest `tools/call` response.

## Message budget: priority packing, instruction never truncated

The block is capped at `max_message_chars` (3000 ≈ 750 tokens). Packing
order: (A) banner + diagnosis, (B) the tool-call instruction with a
seeded first thought, (C) feedback-loop instruction, then (D) retrieved
chunks fill the REMAINING budget, chunk 1 always included (trimmed hard
if needed), further chunks dropped; if no room at all, chunk titles only.
Rationale: chunks are context, the instruction is the payload — a
renderer that lets chunk text truncate the instruction has the priority
backwards. The paste itself is analysed up to `max_paste_chars` 12000;
below `min_paste_chars` 40 the bar answers "paste more" instead.

## Analysis runs off the Tk thread

The bar runs `build_intervention()` in a worker thread (embedding +
DB + retrieval can take seconds); results return to the Tk thread via
the existing queue drain (120 ms), the button disables while busy, and
the finished block is auto-copied to the clipboard — keeping the whole
rescue at exactly two copy-paste round trips.

## Config recipes

All-or-nothing offline (CI, air-gapped): `{"embedding_provider":
"local"}`. Remote Ollama: `{"embedding_provider":"ollama",
"embedding_endpoint":"http://192.168.1.10:11434"}`. LM Studio:
`{"embedding_provider":"lmstudio","embedding_endpoint":
"http://127.0.0.1:1234","embedding_model":"text-embedding-nomic-embed-text-v1.5"}`.
Bigger context for big pastes: raise `max_message_chars` (e.g. 4000) —
chunk budget grows after the must-have parts. More chunks: `top_k: 5`.

## Worked estimate computation

Trace: 96 tokens, 54% repeated 5-grams, 15 retry markers. Memory DB: 57
calibration samples, weighted gap 0.10; recall 0.33 (4 of 12 top paste
tokens found in prior thoughts); wire log: 20 events since last
tools/call. → rep 0.54×25=13.6, calib 0.10×30=3.0, recall
0.33×20=6.7, drop 4 → sum 27.3, ×0.6 = 16.4 → **~16%**, clamped into
[5,45]. The message prints each term so a human can audit: if the
calibration table is empty the term is 0 and says "n/a", never a fudge.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| "No skills folder found" | no *.md (beyond README) in the resolved dir | drop skills in `skills/` or set `intervention.skills_dir` |
| "offline fallback" despite Ollama up | alive check or model mismatch | verify `/api/tags` answers, model name matches `ollama list` |
| retrieval returns wrong skill | vocabulary mismatch between paste and chunks | lead chunks with the exact error strings; re-index (delete skills-index.json) |
| analysis hangs seconds then works | first-run embedding of many files | one-time; later runs hit the cache |
| estimate always ~5% | empty memory DB + non-circular paste | honest floor; record outcomes to feed calibration |
