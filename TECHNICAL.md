# Technical Reference — Plan Audit Map

## 1. Project Identity

| Field | Value |
|-------|-------|
| Package name | `@geeknik/plan-audit-map` |
| Version | 1.0.0 |
| License | MIT |
| Node requirement | >=20 |
| MCP tool name | `plan-audit-map` |
| Executable | `plan-audit-map` → `dist/index.js` |
| Config directory | `~/.plan-audit-map/` (falls back to `~/.code-reasoning/` for backward compat) |

## 2. Architecture

### 2.1 High-Level Flow

```
MCP Client → stdio JSON-RPC → server.ts → cognitive-orchestrator.ts → plugins/memory → response
```

1. **Input validation** — `server.ts` validates tool input against a strict Zod schema; unknown fields are rejected.
2. **Bias detection** — `bias-detector.ts` scans the thought text for known bias patterns.
3. **Cognitive orchestration** — `cognitive-orchestrator.ts` selects reasoning mode, activates plugins, and synthesizes output.
4. **Memory integration** — `sqlite-store.ts` persists thoughts, sessions, and learning patterns; TF-IDF search retrieves relevant history.
5. **Plugin system** — Modular plugins (metacognitive, persona, external-reasoning) contribute perspectives and interventions.
6. **Response synthesis** — Results are packaged with cognitive metrics and returned to the MCP client.

### 2.2 Core Components

| Module | Path | Role |
|--------|------|------|
| Server | `src/server.ts` | MCP protocol handler, input validation, tool registration |
| Cognitive Orchestrator | `src/cognitive/cognitive-orchestrator.ts` | Central coordinator; mode selection, action ranking, recommendation generation |
| Plugin System | `src/cognitive/plugin-system.ts` | Dynamic plugin loading and coordination |
| Metacognitive Plugin | `src/cognitive/plugins/metacognitive-plugin.ts` | Self-reflection, confidence calibration, bias detection |
| Persona Plugin | `src/cognitive/plugins/persona-plugin.ts` | 7 cognitive perspectives (Strategist, Engineer, Skeptic, Creative, Analyst, Pragmatist, Synthesizer) |
| Bias Detector | `src/cognitive/bias-detector.ts` | Pattern-based bias detection with debiasing strategies |
| Insight Detector | `src/cognitive/insight-detector.ts` | Risk signal detection and insight framing |
| State Tracker | `src/cognitive/state-tracker.ts` | Reasoning state management |
| Learning Manager | `src/cognitive/learning-manager.ts` | Multi-armed bandit strategy selection |
| Memory Store | `src/memory/sqlite-store.ts` | SQLite persistence with TF-IDF search |
| Memory Interface | `src/memory/memory-store.ts` | Abstract memory interface |
| Config Manager | `src/utils/config-manager.ts` | Configuration loading and validation |
| Prompt Manager | `src/prompts/manager.ts` | Prompt template management |
| MCP Manager | `src/cognitive/mcp-manager.ts` | External MCP server coordination |

### 2.3 Reasoning Modes

The orchestrator operates in five modes:

| Mode | Trigger | Behavior |
|------|---------|----------|
| `exploration` | Default / early thoughts | Map constraints, catalogue alternatives, defer verdicts |
| `validation` | Strong claim identified | Test the strongest claim with evidence before expanding |
| `revision` | `is_revision: true` | Document belief update: old claim, breaking evidence, new assumption |
| `branching` | `branch_from_thought` set | Compare branch against main path on shared metric |
| `convergence` | Near sequence end | Consolidate into decision with evidence and next action |

Mode shifts are tracked in `recent_mode_shifts[]` with reasons.

### 2.4 Action Ranking

Every response includes `action_ranking` with three slots:

- `primary` — The highest-value next action
- `fallback` — If primary is blocked, the next-best move
- `do_not_do_yet` — Actions to defer until evidence improves

Actions are selected from paraphrase pools (see §4) based on current mode, hypothesis status, confidence level, and detected signals.

### 2.5 Memory System

- **Storage**: SQLite at `~/.plan-audit-map/memory.db`
- **Search**: TF-IDF with intelligent retrieval
- **Patterns**: Experience accumulation and pattern learning
- **Security**: Unsafe IDs rejected; encryption requires `MEMORY_STORE_KEY`

## 3. Changes from Predecessor

### 3.1 Rename

The project was renamed from "Map-Think-Do" to "Plan Audit Map" across all source files, configuration, documentation, and file/directory names.

| Old Identifier | New Identifier |
|----------------|----------------|
| `Map-Think-Do` | `Plan Audit Map` |
| `map-think-do` | `plan-audit-map` |
| `mapthinkdo` | `planauditmap` |
| `MAP_THINK_DO` | `PLAN_AUDIT_MAP` |
| `MCP_MTD` | `PLAN_AUDIT_MAP` |
| `Map.Think.Do` | `Plan.Audit.Map` |

### 3.2 Word Frequency Analysis

A comprehensive scan of the codebase counted occurrences of reasoning/thinking-related terminology:

| Category | Count |
|----------|-------|
| `reasoning` / `thinking` / `thought` family | 2,582 |
| `cognitive` / `metacognitive` family | 625 |
| CoT-related phrases (chain-of-thought, reasoning trace, etc.) | 142 |
| **Total target-word occurrences** | **6,254** |

Top files by terminology density:

| File | Total |
|------|-------|
| `src/server.ts` | 165 |
| `src/cognitive/plugins/persona-plugin.ts` | 151 |
| `test/cognitive-orchestrator.test.ts` | 149 |
| `src/cognitive/cognitive-orchestrator.ts` | 125 |
| `PARAPHRASE_POOLS.md` | 107 |
| `examples/phase5-agi-demo.js` | 95 |
| `src/memory/sqlite-store.ts` | 91 |
| `src/cognitive/consciousness-simulator.ts` | 83 |
| `src/cognitive/plugins/metacognitive-plugin.ts` | 80 |

### 3.3 Safeguards Against CoT Extraction Terminology

The project implements several safeguards to avoid terminology associated with chain-of-thought extraction:

1. **Banned vocabulary** — The paraphrase pools explicitly ban: *metacognitive, persona, vibe, consciousness, energy, mood, resonance*. These words are regression-guarded in tests.

2. **No `**Bold Header**` blocks** — Plugin-era intervention formats with bold headers were removed. All output is inline prose inside JSON payloads.

3. **Categorical labels preserved** — Mode names, hypothesis statuses, bias names, and category IDs are treated as values, not prose. They are never rewritten or paraphrased.

4. **Dynamic slot requirement** — Every rendered string field must be able to differ across consecutive thoughts. Variants either embed a dynamic slot or are wrapped with a context tag.

5. **No reasoning trace exposure** — The system does not expose internal reasoning traces, chain-of-thought sequences, or step-by-step deliberation logs to the MCP client. Output is structured metadata, not raw deliberation.

6. **Heuristic framing** — All cognitive metrics are explicitly documented as heuristics, not calibrated measurements. The README and tool descriptions include disclaimers.

### 3.4 Paraphrase Pool System

The codebase includes an extensive paraphrase pool system (`PARAPHRASE_POOLS.md` + `src/utils/paraphrase-pools.ts`) that provides:

- **25 mode guidance variants** (5 per mode)
- **40+ primary action variants** across branches
- **36+ fallback action variants**
- **36+ deferred action variants**
- **30 mode-shift reasons** (6 per trigger)
- **46 recommendation variants**
- **60 risk guidance variants** (5 per category × 12 categories)
- **18 insight frame variants**
- **32 bias debiasing strategies** + 6 frame variants

Selection uses per-session ring exclusion (last 2 indices) to prevent visible repeats.

## 4. Output Schema

### 4.1 Tool Response Fields

```typescript
{
  // Validated thought flow
  thought: string;
  thought_number: number;
  total_thoughts: number;
  next_thought_needed: boolean;
  is_revision: boolean;
  revises_thought: number | null;
  branch_from_thought: number | null;
  branch_id: string | null;
  needs_more_thoughts: boolean;

  // Cognitive metadata
  cognitive_insights: CognitiveInsight[];
  cognitive_interventions: CognitiveIntervention[];
  hypothesis_ledger: HypothesisEntry[];
  reasoning_mode: ReasoningMode;
  recent_mode_shifts: ModeShift[];
  action_ranking: ActionRanking;
  detected_biases: DetectedBias[];
  ai_recommendations: string[];

  // Metrics (0-1 heuristics)
  metacognitive_awareness: number;
  breakthrough_likelihood: number;
  cognitive_flexibility: number;
  insight_potential: number;
}
```

### 4.2 Cognitive Insight

```typescript
{
  label: string;           // Risk category label
  count: number;           // Marker count in recent window
  guidance: string;        // Specific guidance for this risk
  suggested_validation: string;  // Concrete next check
}
```

### 4.3 Hypothesis Entry

```typescript
{
  statement: string;
  status: 'active' | 'weakening' | 'confirmed' | 'rejected';
  confidence: number;      // 0-1
  next_validation_step: string;
  confidence_change_reason: string;  // Bounded explanation
}
```

## 5. Security Considerations

- Tool input is schema-validated; unknown fields are rejected
- Filesystem-backed memory store rejects unsafe IDs
- Encryption requires `MEMORY_STORE_KEY`; fails closed without it
- Debug logging can expose sensitive input; use only in controlled environments
- Prompt and config file access restricted to configured base directory
- Symlink traversal guards prevent path escapes

## 6. Testing

```bash
npm run build              # TypeScript compilation
npm test                   # Unit + e2e + plugin tests
npm run test:basic         # Basic reasoning flow
npm run test:branch        # Branching logic
npm run test:revision      # Revision capability
npm run test:error         # Error handling
npm run test:perf          # Performance benchmarks
node test/mcp-compliance.test.js    # MCP protocol compliance
node test/transport-failure.test.js # Transport failure handling
```

Tests validate:
- Functional correctness of thought processing
- Reasoning quality and consistency
- Metacognitive awareness accuracy
- Memory integration effectiveness
- Plugin coordination behavior
- Bias detection accuracy
- No banned vocabulary in rendered output
- No identical rendered strings across consecutive thoughts

## 7. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@modelcontextprotocol/sdk` | ^1.26.0 | MCP protocol implementation |
| `better-sqlite3` | ^13.0.3 | SQLite persistence |
| `chalk` | ^5.3.0 | Terminal coloring |
| `mathjs` | ^15.2.0 | Mathematical operations |
| `zod-to-json-schema` | ^3.24.5 | Schema generation |

## 8. File Renames

The following files and directories were renamed during the project rename:

| Old Path | New Path |
|----------|----------|
| `map-think-do.sse.json` | `plan-audit-map.sse.json` |
| `map-think-do.stdio+desk.json` | `plan-audit-map.stdio+desk.json` |
| `map-think-do.stdio.json` | `plan-audit-map.stdio.json` |
| `mapthinkdo_bar.pyw` | `planauditmap_bar.pyw` |
| `mapthinkdo_launcher.py` | `planauditmap_launcher.py` |
| `mapthinkdo_viewer.py` | `planauditmap_viewer.py` |
| `map-think-do-desk-install.skill.md` | `plan-audit-map-desk-install.skill.md` |
| `use-map-think-do-when-stuck.skill.md` | `use-plan-audit-map-when-stuck.skill.md` |
| `map-think-do-tool-schema.skill.md` | `plan-audit-map-tool-schema.skill.md` |
| `mapthinkdo_localhost.bat` | `planauditmap_localhost.bat` |
| `mapthinkdo_local_lan.bat` | `planauditmap_local_lan.bat` |
| `mapthinkdo_remote.bat` | `planauditmap_remote.bat` |
| `mapthinkdo_stdio.bat` | `planauditmap_stdio.bat` |
| `mapthinkdo_token.bat` | `planauditmap_token.bat` |
| `mapthinkdo-desk-launcher.sh` | `planauditmap-desk-launcher.sh` |
| `mapthinkdo_desk/` | `planauditmap_desk/` |
| `map-think-do.e2e.ts` | `plan-audit-map.e2e.ts` |

## 9. Configuration

### 9.1 Environment Variables

| Variable | Purpose |
|----------|---------|
| `MEMORY_STORE_KEY` | Encryption key for memory store (required if encryption enabled) |
| `PLAN_AUDIT_MAP_DEBUG` | Enable debug logging |

### 9.2 Config Directory

Default: `~/.plan-audit-map/`

If `~/.code-reasoning/` exists and `~/.plan-audit-map/` does not, the server uses the legacy directory to avoid orphaning existing data.

### 9.3 MCP Server Config

```json
{
  "mcpServers": {
    "plan-audit-map": {
      "command": "node",
      "args": ["/absolute/path/to/plan-audit-map/dist/index.js"]
    }
  }
}
```

## 10. Known Limitations

- No autonomous execution of external tasks
- No guarantee of correctness for generated recommendations
- No real consciousness, sentience, or AGI
- No public CLI for changing config directory at runtime
- Cognitive metrics are heuristics, not calibrated measurements
- The `decisionFocus` path in the orchestrator currently never fires (`extractDecisionFocus` is a stub returning `undefined`)
