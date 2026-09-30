/**
 * @fileoverview Paraphrase pool engine — per-session rotation, last-2 exclusion,
 * slot-availability guard. Pools are module-level readonly arrays; this utility
 * picks from them without repeating the same index on consecutive thoughts.
 */

/** Indices served in the last 2 picks, per pool id. */
const recentPicks = new Map<string, number[]>();

/** Filter a pool to variants whose ${...} slots are all defined in `slots`. */
function filterBySlots(pool: readonly string[], slots: Record<string, unknown>): string[] {
  return pool.filter(v => {
    const required = v.match(/\$\{(\w+)\}/g);
    if (!required) return true;
    return required.every(m => {
      const key = m.slice(2, -1);
      return slots[key] !== undefined;
    });
  });
}

/** Pick an index from `pool` excluding the last 2 served for `poolId`. */
export function pickFromPool(poolId: string, pool: readonly string[], slots: Record<string, unknown> = {}): string {
  const eligible = filterBySlots(pool, slots);
  if (eligible.length === 0) return pool[0]; // fallback to first variant

  const recent = recentPicks.get(poolId) || [];
  let pick: string;
  let attempts = 0;

  do {
    pick = eligible[Math.floor(Math.random() * eligible.length)];
    attempts++;
  } while (recent.includes(pool.indexOf(pick)) && attempts < 10 && eligible.length > recent.length);

  // Update recent picks ring
  const idx = pool.indexOf(pick);
  recentPicks.set(poolId, [...recent, idx].slice(-2));

  return pick;
}

/** Reset all per-session state (used on session start). */
export function resetParaphraseState(): void {
  recentPicks.clear();
}

/** Substitute ${key} slots in a template using values from `slots`. */
export function fillSlots(template: string, slots: Record<string, unknown>): string {
  return template.replace(/\$\{(\w+)\}/g, (_, key) => {
    const val = slots[key];
    return val !== undefined ? String(val) : `\${${key}}`;
  });
}

/** Pick and fill slots in one call. */
export function renderParaphrase(
  poolId: string,
  pool: readonly string[],
  slots: Record<string, unknown> = {}
): string {
  const template = pickFromPool(poolId, pool, slots);
  return fillSlots(template, slots);
}
