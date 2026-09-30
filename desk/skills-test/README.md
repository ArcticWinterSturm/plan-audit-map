# skills-test/corpus — the originator-written test RAG (~110 KB)

**Premise under test.** Any model handed the source spec can write *a*
skills folder. This corpus is written by the originator of the
plan-audit-map-desk stack, and the difference should be measurable:

1. **Failure signatures, verbatim.** The exact error strings and exit codes
   the stack produces (`SQLite objects created in a thread…`, exit `-11`
   with zero output, `info.This()` compile errors, `Unrecognized key(s) in
   object: 'session_id'`). A spec describes what code does; it does not
   tell you how it fails.
2. **Design rationales.** Why the proxy uses `os.read` and not
   `read(8192)`; why `check_same_thread=False` is safe here; why ordering
   is by `rowid`. These are the "why" facts that turn a hit into a fix.
3. **Field-tested compatibility matrix.** better-sqlite3 × Node versions,
   confirmed by install attempts — including the Node ≥ 26 break and its
   exact pin.
4. **Cross-file invariants.** Which process writes which table, which port,
   which env var — the map that only the person who wired it holds.
5. **Vocabulary discipline for retrieval.** Sections lead with the words a
   circling trace actually contains, because retrieval is lexical+embedding
   hybrid and the corpus author controls both sides.

## Layout
- `*.skill.md` (14 files, 100–120 KB total) — indexed by the intervention
  engine. Sections are `##`-cut retrieval units, self-contained, most under
  ~1400 chars (the chunker's window size).
- This README is **not indexed** (the indexer skips `README*`).

## Run the evaluation
```bash
cd plan-audit-map-desk/skills-test
python3 rag_eval.py
```
It builds the real index (`desk/mtd_intervention.py`) over this corpus with
the deterministic offline embedder, fires ~20 synthetic circling traces
(each labelled with the skill that must be retrieved), and prints top-1 /
top-3 hit rates plus structural checks (size budget, section discipline).
Exit code 0 = pass.

## Swapping this corpus into the bar
Set `intervention.skills_dir` in `~/.plan-audit-map/desk-bar.json` to this
`corpus/` directory (or drop the `*.skill.md` files into `skills/`).

## Scorecard (v1.1.1, deterministic — identical across runs)

- Retrieval: top-1 **86 %** (18/21, threshold 70 %), top-3 **100 %**
  (21/21, threshold 90 %) against the real engine (offline hashed
  embedder, `desk/mtd_intervention.py` chunking + hybrid search).
- Corpus: 18 files, 104,814 bytes (102.4 KB, target 100–120 KB),
  175 chunks, every file `# `-titled with ≥ 3 `## ` sections, no chunk
  over the 1400-char window + slack.
- The three top-1 misses (viewer empty-DB crash, Qwen runner rewrite,
  npm prepare-chunk) all retrieve `desk-stack-triage-index` first —
  which routes to the correct fix skill — and the correct skill is
  always within top-3.
- Run it: `python3 rag_eval.py` (verbose: `-v`). Exit 0 = pass.
