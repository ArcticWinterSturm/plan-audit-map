# skills/ — the ONE folder the Intervention Paste Bar indexes

Drop `*.md` skill documents here. The desk bar's **Intervene** tab chunks
every file (excluding this README), embeds the chunks, caches the index at
`~/.plan-audit-map/skills-index.json`, and retrieves the top matches whenever
you paste a circling agent's output.

## Format that works best
- One skill per file, `# Title: …` first line.
- `##` sections become retrieval units; keep a section self-contained
  (a symptom→cause→fix table, a procedure, a schema) so a retrieved chunk
  is useful alone. Sections longer than ~1400 chars get windowed.
- Lead sections with the vocabulary the failure will actually contain
  (error strings, tool names, file names) — retrieval is embedding-based,
  and circling traces quote those verbatim.
- No filler ("I think", "it seems") — stored prose should be checkable.

## Embedding provider (pick automatically, in this order)
1. **Ollama** `http://127.0.0.1:11434`, model `nomic-embed-text`
   (`ollama pull nomic-embed-text`) — fast, local, recommended.
2. **LM Studio** `http://127.0.0.1:1234` (OpenAI-compatible endpoint).
3. **Offline fallback** — deterministic hashed n-gram vectors (no server,
   no semantic understanding, still finds documents by shared vocabulary).

Override in `~/.plan-audit-map/desk-bar.json` under `intervention`:
`embedding_provider` (auto | ollama | lmstudio | nomic | local),
`embedding_endpoint`, `embedding_model`, `top_k`, `min_score`.

## Shipped skills
- `plan-audit-map-desk-install.skill.md` — install/verify/relocate procedure
  (distilled from a successful agent install).
- `use-plan-audit-map-when-stuck.skill.md` — re-entry playbook for circular
  CoT; the schema, the rules, the feedback loop.
- `mcp-wiring-qwen-claude.skill.md` — client wiring incl. Qwen's
  non-standard desktop bridge and its runner-rewriting traps.
- `wiretap-viewer-troubleshooting.skill.md` — symptom/cause/fix table for
  the tap, the DB and the viewer.
