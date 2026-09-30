# Plan Audit Map

## What Problem Does It Solve?

ChatGPT and Claude conspiring in neuralese while clobbering your code in secret and committing unprompted cybercrimes from your paid quota.

## Attribution

This project is a fork of [mettamatt/code-reasoning](https://github.com/mettamatt/code-reasoning) (also known as "Sequential Thinking"), originally created by Matt Westgate. The original introduced structured cognitive reasoning over MCP. This fork extends it with a cognitive orchestrator, bias detection, action ranking, paraphrase pools, a Python desk stack (taskbar bar, SQL viewer, wire tap, intervention paste bar), and SQLite persistence.

---

## What It Is

An MCP (Model Context Protocol) server that exposes a single `plan-audit-map` tool for structured problem solving. It processes ordered thoughts with revision and branching semantics, generates cognitive metadata (bias detection, action rankings, insight signals), and persists everything to SQLite.

The project includes a **Python desk stack** — a taskbar bar, SQL viewer, wire tap, and intervention paste bar — that makes the MCP server's activity visible and actionable in real time.

## Components

### MCP Server (TypeScript)

The core is an MCP server that accepts structured thought input and returns cognitive analysis:

- **Cognitive Orchestrator** — Central coordinator that selects reasoning mode, activates plugins, and synthesizes output
- **Bias Detector** — Pattern-based detection of 8 cognitive biases (confirmation, overconfidence, anchoring, availability, sunk cost, framing, hindsight, fundamental attribution) with debiasing strategies
- **Insight Detector** — Risk signal detection across 12 categories (correctness, regression, verification gap, coupling, concurrency, data integrity, failure modes, security, performance, maintainability, tradeoff, reversibility)
- **Action Ranking** — Ranks next actions (primary / fallback / do-not-do-yet) based on current mode, hypothesis status, and confidence
- **Paraphrase Pools** — 400+ string variants across all output surfaces, with per-session ring exclusion to prevent visible repeats
- **Memory Store** — SQLite persistence with TF-IDF search and pattern learning
- **Plugin System** — Modular plugins: metacognitive (self-reflection, confidence calibration), persona (7 cognitive perspectives), external-reasoning (tool integration)
- **Multiple Transports** — stdio, SSE, LAN, remote tunnel (ngrok/pinggy/localhostrun), token auth

### Desk Stack (Python, stdlib-only)

A drop-in companion that makes the server visible and actionable:

- **Taskbar Desk Bar** (Windows) — Win32 appbar that shows recent activity, a ticker of the last tool call, and a one-button SQL viewer launcher. Tabbed overview: Recent activity + Intervene.
- **SQL Viewer** (Tkinter) — Browse sessions, thought timeline, branch/revision graph, analytics, search, bookmarks, export, and a conversation transcript built from the wire capture.
- **Wire Tap / Launcher** — A transparent stdio proxy that records every MCP request/response pair so conversations are visible in the viewer. Fixes: raw `os.read()` (no BufferedReader deadlock), EOF forwarding, `check_same_thread=False` for SQLite.
- **Intervention Paste Bar** (v1.1) — Paste a circling agent's last messages, get back a copy-paste rescue block. Runs entirely local: skills-folder chunking with embeddings (Ollama/LM Studio/offline hashed), memory DB mining for prior work, circularity diagnostics (repeated-5-gram ratio, longest repeated block, retry/hedge markers), and a measured improvement estimate with shown arithmetic.
- **Auto-Installer** — `install.bat` (Windows) / `install.sh` (Linux/macOS) — finds the repo, overlays server sources, npm installs, builds, writes config, resolves MCP connection JSONs.

### Reasoning Modes

The orchestrator operates in five modes:

| Mode | Trigger | Behavior |
|------|---------|----------|
| `exploration` | Default / early thoughts | Map constraints, catalogue alternatives, defer verdicts |
| `validation` | Strong claim identified | Test the strongest claim with evidence before expanding |
| `revision` | `is_revision: true` | Document belief update: old claim, breaking evidence, new assumption |
| `branching` | `branch_from_thought` set | Compare branch against main path on shared metric |
| `convergence` | Near sequence end | Consolidate into decision with evidence and next action |

## Installation

### MCP Server

```bash
npm install
npm run build
node dist/index.js
```

### Desk Stack

**Windows:**
```bat
install.bat
```

**Linux / macOS:**
```bash
./install.sh
```

Requirements: Node >= 20, Python 3.9+ (desk stack only). No pip packages — the desk stack is 100% stdlib.

## MCP Configuration

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

For desk recording + bar, use `connect/plan-audit-map.stdio+desk.json` after running the installer.

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

Required: `thought`, `thought_number`, `total_thoughts`, `next_thought_needed`.

## Output Shape

Responses include the validated thought flow plus:

- `cognitive_insights` — Detected patterns and risk signals
- `cognitive_interventions` — Bounded activation context for interventions
- `hypothesis_ledger` — Tracked hypotheses with confidence and status
- `reasoning_mode` — Current mode
- `recent_mode_shifts` — History of mode transitions with reasons
- `action_ranking` — Ranked next actions with rationales (primary / fallback / do-not-do-yet)
- `detected_biases` — Cognitive biases found with debiasing strategies
- `ai_recommendations` — Suggested next steps
- `metacognitive_awareness` — Self-reflection depth (0-1)
- `breakthrough_likelihood` — Discovery probability (0-1)
- `cognitive_flexibility` — Adaptability measure (0-1)
- `insight_potential` — Potential for novel insights (0-1)

These values are heuristics, not calibrated scientific measurements.

## Paraphrase Pool System

The codebase includes 400+ string variants across all output surfaces:

- 25 mode guidance variants (5 per mode)
- 40+ primary action variants across branches
- 36+ fallback action variants
- 36+ deferred action variants
- 30 mode-shift reasons (6 per trigger)
- 46 recommendation variants
- 60 risk guidance variants (5 per category x 12 categories)
- 18 insight frame variants
- 32 bias debiasing strategies + 6 frame variants

Selection uses per-session ring exclusion (last 2 indices) to prevent visible repeats. Every rendered string field must be able to differ across consecutive thoughts.

## Safeguards

1. **Banned vocabulary** — metacognitive, persona, vibe, consciousness, energy, mood, resonance are regression-guarded in tests
2. **No bold-header blocks** — All output is inline prose inside JSON payloads
3. **Categorical labels preserved** — Mode names, hypothesis statuses, bias names are values, not prose
4. **Dynamic slot requirement** — Every rendered string differs across thoughts
5. **No reasoning trace exposure** — Output is structured metadata, not raw deliberation
6. **Heuristic framing** — All metrics documented as heuristics

## Development

```bash
npm run build          # Compile TypeScript
npm test               # Unit + e2e + plugin tests
npm run test:basic     # Basic reasoning flow
npm run test:branch    # Branching logic
npm run test:revision  # Revision capability
npm run test:error     # Error handling
npm run test:perf      # Performance benchmarks
npm run lint           # ESLint
npm run format         # Prettier
```

## Documentation

- [Technical Reference](./TECHNICAL.md) — Architecture, changes, implementation details
- [Desk Stack README](./desk/README.md) — Desk bar, viewer, wire tap, intervention paste bar
- [Configuration](./docs/configuration.md)
- [Testing](./docs/testing.md)

## License
MIT
