# Plan Audit Map

## What Problem Does It Solve?

ChatGPT and Claude conspiring in neuralese while clobbering your code in secret and committing unprompted cybercrimes from your paid quota.

## Attribution

This project is a fork of [mettamatt/code-reasoning](https://github.com/mettamatt/code-reasoning) (also known as "Sequential Thinking"), originally created by Matt Westgate. The original project introduced the concept of structured cognitive reasoning over MCP. This fork extends the original with additional cognitive signals, bias detection, action ranking, and a comprehensive paraphrase pool system.

---

An MCP (Model Context Protocol) server that provides structured problem-solving capabilities through a single `plan-audit-map` tool. It supports linear reasoning, revisions, branching, prompt templates, persisted memory, and heuristic cognitive signals such as bias detection and recommendation generation.

## Overview

Plan Audit Map is an experimental reasoning aid and orchestration layer. It exposes a single MCP tool that accepts structured thought input and returns cognitive metadata, action rankings, bias detection, and recommendations. It is **not** a claim of sentience or general intelligence.

## Features

- **Structured Thought Processing** — Accepts ordered thoughts with optional revision and branch metadata
- **Cognitive State Metadata** — Generates `metacognitive_awareness`, `breakthrough_likelihood`, `cognitive_flexibility`, and related signals
- **Bias Detection** — Heuristic detection of common cognitive biases with debiasing strategies
- **Action Ranking** — Ranks next actions based on current reasoning mode and context
- **Persistent Memory** — SQLite-backed storage with TF-IDF search and pattern learning
- **Prompt Templates** — Modular prompt system with plugin architecture
- **Multi-Persona Reasoning** — 7 cognitive perspectives (Strategist, Engineer, Skeptic, Creative, Analyst, Pragmatist, Synthesizer)
- **Revision & Branching** — Full support for belief updates and parallel exploration paths

## Installation

```bash
npm install
npm run build
```

Run the server:

```bash
node dist/index.js
```

## MCP Configuration

Example Claude Desktop configuration:

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

## Tool Input

```json
{
  "thought": "Investigate the failing request path",
  "thought_number": 1,
  "total_thoughts": 4,
  "next_thought_needed": true,
  "is_revision": false,
  "revises_thought": null,
  "branch_from_thought": null,
  "branch_id": null,
  "needs_more_thoughts": false
}
```

Required fields: `thought`, `thought_number`, `total_thoughts`, `next_thought_needed`.

Branching requires both `branch_from_thought` and `branch_id`. Revisions require `is_revision: true` and `revises_thought`.

## Output Shape

Responses include the validated thought flow plus cognitive metadata:

- `cognitive_insights` — Detected patterns and risk signals
- `cognitive_interventions` — Bounded activation context for interventions
- `hypothesis_ledger` — Tracked hypotheses with confidence and status
- `reasoning_mode` — Current mode (exploration, validation, revision, branching, convergence)
- `recent_mode_shifts` — History of mode transitions with reasons
- `action_ranking` — Ranked next actions with rationales
- `detected_biases` — Cognitive biases found with debiasing strategies
- `ai_recommendations` — Suggested next steps
- `metacognitive_awareness` — Self-reflection depth (0-1)
- `breakthrough_likelihood` — Discovery probability (0-1)
- `cognitive_flexibility` — Adaptability measure (0-1)
- `insight_potential` — Potential for novel insights (0-1)

These values are heuristics produced by the current implementation. They are useful for downstream prompts and debugging, but they are not formal guarantees or calibrated scientific measurements.

## Development

```bash
npm run build          # Compile TypeScript
npm test               # Run tests
npm run test:basic     # Basic reasoning tests
npm run test:branch    # Branching logic tests
npm run test:revision  # Revision capability tests
npm run test:error     # Error handling tests
npm run test:perf      # Performance tests
npm run lint           # ESLint
npm run format         # Prettier
```

## Documentation

- [Technical Reference](./TECHNICAL.md) — Architecture, changes, and implementation details
- [Configuration](./docs/configuration.md)
- [Testing](./docs/testing.md)

## License

MIT
