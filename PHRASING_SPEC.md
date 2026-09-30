# Paraphrase Specification — Cognitive Output Templates

## Summary

| File | Template Count | Paraphrases Needed |
|------|---------------|-------------------|
| `cognitive/plugins/metacognitive-plugin.ts` | 13 | 40+ |
| `cognitive/plugins/persona-plugin.ts` | 5 | 15+ |
| `cognitive/cognitive-orchestrator.ts` | 8 | 20+ |
| `cognitive/insight-detector.ts` | ✅ fixed | — |
| `cognitive/state-tracker.ts` | ✅ fixed | — |
| `cognitive/bias-detector.ts` | 1 | 3 |

---

## 1. `cognitive/plugins/metacognitive-plugin.ts`

### 1.1 `generateConfidenceCalibration` (lines 405-430)
**Current:** 3 static variants, randomly selected.
**Problem:** All 3 start with `**Confidence Check**` / `**Reality Check**` / `**Evidence Audit**` — same structure, same questions.

**Paraphrase pool needed: 8+ variants**
- Vary the header: `**Calibration**`, `**Confidence Audit**`, `**Evidence Check**`, `**Reality Test**`
- Vary the framing: question-based, directive-based, or evidence-based
- Include dynamic values: `confidence_level`, `complexity`, `scope_uncertainty`
- Example directive variant: `"Confidence is at ${confidence_level}% on a ${complexity}/10 problem. Name one piece of evidence that would lower it."`

### 1.2 `generateAssumptionQuestioning` (line 438)
**Current:** 1 static template with `**Assumption Check**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Assumptions**`, `**What Are We Assuming?**`, `**Unstated Premises**`
- Vary the follow-up questions (currently 5 identical bullet points every time)
- Include dynamic: number of assumptions found, the assumptions themselves

### 1.3 `generateAlternativeGeneration` (line 456)
**Current:** 1 static template with `**Alternative Thinking**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Alternatives**`, `**Other Paths**`, `**Solution Space**`
- Vary the "Different Approaches" bullets
- Vary the "Perspective Shifts" bullets
- Include dynamic: domain, complexity

### 1.4 `generateBiasDetection` (line 480)
**Current:** 1 static template with `**Bias Alert**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Bias Check**`, `**Potential Bias: ${detectedBias}**`, `**Watch For: ${detectedBias}**`
- Vary the "Debiasing Strategies" bullets
- Vary the "Critical Questions" bullets
- Include dynamic: detectedBias name, evidence

### 1.5 `generateReasoningEvaluation` (line 502)
**Current:** 1 static template with `**Reasoning Audit**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Reasoning Quality**`, `**Process Check**`, `**Thinking Audit**`
- Vary the evaluation criteria
- Include dynamic: complexity, thought_count

### 1.6 `generateUncertaintyAcknowledgment` (line 529)
**Current:** 1 static template with `**Uncertainty Reality**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**What We Don't Know**`, `**Uncertainty**`, `**Unknowns**`
- Vary the framing
- Include dynamic: confidence_level, scope_uncertainty

### 1.7 `generatePerspectiveShift` (line 555)
**Current:** 1 static template with `**Perspective Shift**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Reframe**`, `**Different Angle**`, `**Step Back**`
- Vary the perspective prompts
- Include dynamic: thought_history length, top theme

### 1.8 `identifyLikelyBias` (lines 650-652)
**Current:** 3 hard-coded return strings.
**Paraphrase pool needed: 8+ variants**
- Map to actual bias names from bias-detector.ts
- Include dynamic: confidence_level, trigger words found

### 1.9 `generateActivationReason` (lines 707-711)
**Current:** 4 static strings based on `need` threshold.
**Paraphrase pool needed: 8+ variants**
- Include dynamic: `need` score, `metacognitiveNeed`, `complexityFactor`
- Example: `"Metacognitive need: ${need.toFixed(2)} (confidence/complexity mismatch: ${mismatch.toFixed(2)})"`

---

## 2. `cognitive/plugins/persona-plugin.ts`

### 2.1 `generatePersonaPerspective` (lines 711, 737)
**Current:** 2 static templates for single-persona output.
**Paraphrase pool needed: 6+ variants per persona**
- Vary the header: `**${persona.name}**`, `**Through ${persona.name}'s Eyes**`, `**${persona.name}'s Take**`
- Vary the recommendation/concern framing
- Include dynamic: persona.strengths[0], persona.weaknesses[0]

### 2.2 `generateSynthesis` (line 757)
**Current:** 1 static template with `**Multi-Perspective Analysis**` header.
**Paraphrase pool needed: 6+ variants**
- Header variations: `**Synthesis**`, `**Combined View**`, `**Where Perspectives Meet**`
- Vary the disagreement/synthesis framing
- Include dynamic: persona names, disagreement topic

### 2.3 `buildDecisionFocus` (line 932)
**Current:** 1 static template for tradeoff summary.
**Paraphrase pool needed: 6+ variants**
- Vary the tradeoff framing
- Vary the "primary action" phrasing
- Include dynamic: persona names, stance

---

## 3. `cognitive/cognitive-orchestrator.ts`

### 3.1 `generatePrimaryAction` (line 1363)
**Current:** 1 static template.
**Paraphrase pool needed: 6+ variants**
- Vary the action framing
- Include dynamic: topHypothesis.statement, action signals

### 3.2 `buildActionFallback` (line ~1380)
**Current:** 1 static template.
**Paraphrase pool needed: 6+ variants**
- Vary the fallback framing
- Include dynamic: top hypothesis status

### 3.3 `buildActionDefer` (line ~1395)
**Current:** 1 static template.
**Paraphrase pool needed: 6+ variants**
- Vary the deferral framing
- Include dynamic: mode, signals

### 3.4 `getReasoningModeGuidance` (lines 1522-1531)
**Current:** 5 static strings (one per mode).
**Paraphrase pool needed: 3+ variants per mode (15 total)**
- exploration: `"map constraints and alternatives before committing"` → vary
- validation: `"test the strongest claim with evidence before widening"` → vary
- revision: `"document what changed and why"` → vary
- branching: `"compare this branch against main path"` → vary
- convergence: `"summarize decision and next action"` → vary
- Include dynamic: thought_count, confidence_level

---

## 4. `cognitive/bias-detector.ts`

### 4.1 `selectDebisingStrategies` (line 492)
**Current:** Returns top 2 from static list.
**Problem:** Always returns the first 2 strategies, not the most relevant.
**Fix:** Shuffle or select based on evidence match. Return 2-3 strategies.

---

## 5. Implementation Notes

### Selection Strategy
- Use `Math.floor(Math.random() * pool.length)` for random selection
- Track last N selections to avoid immediate repeats within a session
- Weight toward higher-impact variants when confidence is high

### Dynamic Value Injection
Every paraphrase MUST include at least ONE dynamic value:
- `confidence_level` → formatted as % or 0.XX
- `complexity` → shown as N/10
- `thought_count` → shown as integer
- `scope_uncertainty` → shown as 0.XX
- `detectedBias` → bias name string
- `topHypothesis.statement` → truncated to 50 chars
- `persona.name` → persona display name
- `theme` → detected theme word

### What NOT to Paraphrase
- JSON field names (`session_id`, `thought_number`, etc.)
- Boolean values (`true`, `false`)
- Numeric IDs
- Categorical labels (`critical`, `degraded`, `healthy` for health status)
- Mode names (`exploration`, `validation`, `convergence`, etc.)

### Testing
After implementing paraphrases:
1. Run `npm run build` — must pass
2. Run `npm test` — must pass
3. Run 10 consecutive thoughts through the server — no identical strings should appear in the output
