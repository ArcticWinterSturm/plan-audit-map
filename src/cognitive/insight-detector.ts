import { MemoryStore, StoredThought } from '../memory/memory-store.js';
import { CognitiveContext, PluginIntervention } from './plugin-system.js';
import { CognitiveState } from './state-tracker.js';
import { renderParaphrase } from '../utils/paraphrase.js';
import { POOL_INSIGHT_DESCRIPTION, POOL_INSIGHT_IMPLICATIONS } from '../utils/paraphrase-pools.js';

export interface CognitiveInsight {
  type: 'pattern_recognition' | 'breakthrough' | 'synthesis' | 'paradigm_shift';
  confidence: number;
  description: string;
  implications: string[];
  evidence: string[];
  novelty_score: number;
  impact_potential: number;
  evidence_strength?: number;
  validation_priority?: number;
  suggested_validation?: string;
}

export class InsightDetector {
  private readonly insightHistory: CognitiveInsight[] = [];

  constructor(
    private readonly memoryStore: MemoryStore | undefined,
    _state: CognitiveState,
    _performanceMetrics: Map<string, number>
  ) {}

  public getHistory(): CognitiveInsight[] {
    return [...this.insightHistory];
  }

  public async detectInsights(
    context: CognitiveContext,
    interventions: PluginIntervention[]
  ): Promise<CognitiveInsight[]> {
    const insights: CognitiveInsight[] = [];

    insights.push(...(await this.detectPatternInsights(context)));
    insights.push(...(await this.detectBreakthroughs(context, interventions)));
    insights.push(...(await this.detectSynthesis(context, interventions)));

    const rankedInsights = insights
      .map(insight => this.enrichInsight(context, insight))
      .sort((a, b) => {
        const priorityDelta = (b.validation_priority || 0) - (a.validation_priority || 0);
        if (priorityDelta !== 0) return priorityDelta;
        return (b.evidence_strength || 0) - (a.evidence_strength || 0);
      });

    this.insightHistory.push(...rankedInsights);
    if (this.insightHistory.length > 50) {
      this.insightHistory.splice(0, this.insightHistory.length - 50);
    }
    return rankedInsights;
  }

  private async detectPatternInsights(context: CognitiveContext): Promise<CognitiveInsight[]> {
    const insights: CognitiveInsight[] = [];
    if (!this.memoryStore) return insights;
    try {
      const recent = context.thought_history.slice(-10);
      const themes = this.extractThemes(recent);
      const recurring = themes.filter(t => t.frequency >= 3);
      for (const theme of recurring) {
        const slots = {
          label: theme.pattern,
          count: theme.frequency,
          history: context.thought_history.length,
          thought_number: context.thought_history[context.thought_history.length - 1]?.thought_number || 0,
        };
        insights.push({
          type: 'pattern_recognition',
          description: renderParaphrase('insight:description', POOL_INSIGHT_DESCRIPTION, slots),
          confidence: Math.min(0.9, theme.frequency / 5),
          impact_potential: 0.6,
          implications: [renderParaphrase('insight:implications', POOL_INSIGHT_IMPLICATIONS, slots)],
          evidence: theme.contexts,
          novelty_score: 0.3,
        });
      }
    } catch (err) {
      console.error('pattern insight error', err);
    }
    return insights;
  }

  private async detectBreakthroughs(
    context: CognitiveContext,
    interventions: PluginIntervention[]
  ): Promise<CognitiveInsight[]> {
    const insights: CognitiveInsight[] = [];
    const breakthroughScore = this.calculateBreakthroughScore(context, interventions);
    if (breakthroughScore > 0.7) {
      insights.push({
        type: 'breakthrough',
        description: 'Possible cognitive breakthrough detected',
        confidence: breakthroughScore,
        impact_potential: 0.8,
        implications: ['May accelerate problem solving'],
        evidence: [context.current_thought || ''],
        novelty_score: 0.8,
      });
    }
    return insights;
  }

  private async detectSynthesis(
    context: CognitiveContext,
    interventions: PluginIntervention[]
  ): Promise<CognitiveInsight[]> {
    const insights: CognitiveInsight[] = [];
    const perspectives = interventions.map(i => i.metadata.plugin_id);
    const unique = new Set(perspectives);
    if (unique.size > 1) {
      insights.push({
        type: 'synthesis',
        description: `Synthesis of ${unique.size} perspectives`,
        confidence: 0.7,
        impact_potential: 0.7,
        implications: ['Multiple viewpoints merged'],
        evidence: Array.from(unique),
        novelty_score: 0.6,
      });
    }
    return insights;
  }

  private extractThemes(
    thoughts: StoredThought[]
  ): Array<{ pattern: string; frequency: number; contexts: string[] }> {
    const themeMap = new Map<string, { count: number; contexts: Set<string> }>();
    const stopWords = new Set([
      'about', 'above', 'after', 'again', 'against', 'allow', 'alone', 'along',
      'already', 'also', 'although', 'always', 'among', 'another', 'anyone',
      'anything', 'around', 'asked', 'available', 'away', 'based', 'because',
      'become', 'been', 'before', 'being', 'below', 'between', 'both',
      'called', 'came', 'cannot', 'could', 'current', 'different', 'does',
      'doing', 'done', 'down', 'during', 'each', 'either', 'enough',
      'every', 'example', 'first', 'found', 'from', 'further', 'gets',
      'getting', 'given', 'going', 'gone', 'gotten', 'great', 'had',
      'have', 'having', 'here', 'however', 'just', 'keep', 'kept',
      'kind', 'knew', 'know', 'known', 'last', 'later', 'least', 'less',
      'like', 'likely', 'little', 'long', 'longer', 'look', 'looking',
      'looked', 'made', 'make', 'making', 'many', 'maybe', 'might', 'more',
      'most', 'much', 'must', 'never', 'next', 'nothing', 'number', 'often',
      'once', 'only', 'other', 'others', 'over', 'part', 'perhaps',
      'place', 'point', 'possible', 'probably', 'put', 'quite', 'rather',
      'really', 'right', 'said', 'same', 'saying', 'second', 'seem',
      'seemed', 'seems', 'several', 'shall', 'should', 'since', 'something',
      'still', 'such', 'take', 'taken', 'tell', 'than', 'that', 'their',
      'them', 'then', 'there', 'these', 'they', 'thing', 'those', 'thought',
      'through', 'together', 'told', 'took', 'toward', 'tried', 'try',
      'trying', 'turn', 'turned', 'two', 'under', 'upon', 'using', 'very',
      'want', 'was', 'well', 'went', 'were', 'what', 'when', 'where',
      'which', 'while', 'who', 'why', 'will', 'with', 'within',
      'without', 'work', 'would', 'yet', 'your',
    ]);
    
    thoughts.forEach(t => {
      const words = t.thought
        .toLowerCase()
        .split(/\s+/)
        .filter(w => w.length > 4 && !stopWords.has(w));
      words.forEach(word => {
        const cur = themeMap.get(word) || { count: 0, contexts: new Set<string>() };
        cur.count++;
        // Extract sentence-level excerpts containing the theme word
        const sentences = t.thought.split(/[.!?;]\s+/);
        const matchingSentence = sentences.find(s => 
          s.toLowerCase().includes(word) && s.trim().length > 10
        );
        if (matchingSentence) {
          cur.contexts.add(matchingSentence.trim().slice(0, 120));
        } else {
          cur.contexts.add(t.thought.slice(0, 80));
        }
        themeMap.set(word, cur);
      });
    });
    return Array.from(themeMap.entries()).map(([pattern, data]) => ({
      pattern,
      frequency: data.count,
      contexts: Array.from(data.contexts),
    }));
  }

  private calculateBreakthroughScore(
    context: CognitiveContext,
    interventions: PluginIntervention[]
  ): number {
    let score = 0;
    score += Math.min(0.3, interventions.length * 0.1);
    score += context.metacognitive_awareness * 0.3;
    score += context.creative_pressure * 0.2 + context.confidence_level * 0.2;
    return Math.min(1, score);
  }

  private enrichInsight(context: CognitiveContext, insight: CognitiveInsight): CognitiveInsight {
    const evidence_strength = this.calculateEvidenceStrength(insight);
    const suggested_validation = this.buildSuggestedValidation(context, insight);
    const validation_priority = this.calculateValidationPriority(
      context,
      insight,
      evidence_strength
    );

    return {
      ...insight,
      evidence_strength,
      validation_priority,
      suggested_validation,
    };
  }

  private calculateEvidenceStrength(insight: CognitiveInsight): number {
    const normalizedEvidence = insight.evidence
      .map(entry => entry.trim())
      .filter(entry => entry.length > 0);

    if (normalizedEvidence.length === 0) {
      return 0.1;
    }

    const uniqueEvidence = new Set(normalizedEvidence).size;
    const evidenceCountScore = Math.min(1, uniqueEvidence / 3);
    const directEvidenceCount = normalizedEvidence.filter(
      entry => !/current reasoning|current thought/i.test(entry)
    ).length;
    const directEvidenceScore = directEvidenceCount / normalizedEvidence.length;
    const evidenceSpecificityScore =
      normalizedEvidence.reduce((sum, entry) => sum + Math.min(1, entry.length / 60), 0) /
      normalizedEvidence.length;

    return Math.min(
      1,
      evidenceCountScore * 0.4 + directEvidenceScore * 0.35 + evidenceSpecificityScore * 0.25
    );
  }

  private calculateValidationPriority(
    context: CognitiveContext,
    insight: CognitiveInsight,
    evidence_strength: number
  ): number {
    const urgencyScore = context.urgency === 'high' ? 1 : context.urgency === 'medium' ? 0.6 : 0.3;
    const actionabilityScore = insight.implications.length > 0 ? 0.8 : 0.4;
    const unresolvedPotential = 1 - evidence_strength;

    const rawScore =
      evidence_strength * 0.3 +
      insight.impact_potential * 0.25 +
      insight.confidence * 0.2 +
      actionabilityScore * 0.1 +
      urgencyScore * 0.1 +
      unresolvedPotential * 0.05;

    return Math.min(1, rawScore);
  }

  private buildSuggestedValidation(context: CognitiveContext, insight: CognitiveInsight): string {
    const theme = insight.description.replace('Recurring theme: ', '').replace(/"/g, '');
    
    switch (insight.type) {
      case 'pattern_recognition': {
        const action = this.getThemeValidationAction(theme);
        return `${action} for "${theme}" and verify it changes the next decision.`;
      }
      case 'breakthrough':
        return context.confidence_level > 0.7
          ? 'Stress-test the new conclusion against the strongest counterexample before committing to it.'
          : 'Run a small validation step that confirms the assumption driving this apparent breakthrough.';
      case 'synthesis':
        return 'Compare the synthesized approach against the best single-perspective alternative on risk, cost, and reversibility.';
      case 'paradigm_shift':
        return 'Verify that the reframed model explains the existing evidence better than the previous one.';
      default:
        return 'Validate this insight against the most relevant evidence before building further reasoning on top of it.';
    }
  }

  private getThemeValidationAction(theme: string): string {
    const lower = theme.toLowerCase();
    if (lower.includes('migration') || lower.includes('refactor')) return 'Find a concrete example';
    if (lower.includes('performance') || lower.includes('bottleneck')) return 'Identify the measurement';
    if (lower.includes('security') || lower.includes('vulnerability')) return 'Locate the attack surface';
    if (lower.includes('scal') || lower.includes('growth')) return 'Check the load assumption';
    if (lower.includes('cost') || lower.includes('budget') || lower.includes('roi')) return 'Verify the unit economics';
    if (lower.includes('user') || lower.includes('ux') || lower.includes('interface')) return 'Find the behavioral signal';
    if (lower.includes('data') || lower.includes('schema') || lower.includes('model')) return 'Check the data shape';
    if (lower.includes('test') || lower.includes('bug') || lower.includes('error')) return 'Reproduce the failure';
    if (lower.includes('deploy') || lower.includes('release') || lower.includes('ship')) return 'Verify the rollback path';
    if (lower.includes('design') || lower.includes('architect')) return 'Stress-test the boundary';
    return 'Check whether this pattern appears in at least one additional concrete example';
  }
}
