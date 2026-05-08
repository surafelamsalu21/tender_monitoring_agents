/** Maps screening.step2.strategic_signals engagement tokens to UI labels and sort order. */

export type EngagementKind = 'advisory_only' | 'mixed' | 'supply_only';

export type EngagementFilter = 'all' | 'advisory' | 'mixed' | 'supply';

const TOKEN_ADVISORY = 'engagement_advisory_only';
const TOKEN_MIXED = 'engagement_advisory_and_supply_mixed';
const TOKEN_SUPPLY = 'engagement_supply_only';

export function parseEngagementFromSignals(
  strategicSignals?: string[] | null
): EngagementKind | null {
  const s = strategicSignals ?? [];
  if (s.includes(TOKEN_ADVISORY)) return 'advisory_only';
  if (s.includes(TOKEN_MIXED)) return 'mixed';
  if (s.includes(TOKEN_SUPPLY)) return 'supply_only';
  return null;
}

/** Higher = show first when sorting "Advisory first". */
export function engagementSortRank(strategicSignals?: string[] | null): number {
  const k = parseEngagementFromSignals(strategicSignals);
  if (k === 'advisory_only') return 3;
  if (k === 'mixed') return 2;
  if (k === 'supply_only') return 1;
  return 0;
}

export function engagementBadgeDisplay(strategicSignals?: string[] | null): {
  label: string;
  className: string;
  kind: EngagementKind;
} | null {
  const k = parseEngagementFromSignals(strategicSignals);
  if (!k) return null;
  if (k === 'advisory_only') {
    return {
      kind: k,
      label: 'Advisory',
      className:
        'text-violet-800 bg-violet-100 border-violet-200',
    };
  }
  if (k === 'mixed') {
    return {
      kind: k,
      label: 'Advisory + supply',
      className:
        'text-indigo-900 bg-indigo-100 border-indigo-200',
    };
  }
  return {
    kind: k,
    label: 'Supply',
    className: 'text-slate-800 bg-slate-100 border-slate-300',
  };
}

export function tenderMatchesEngagementFilter(
  strategicSignals: string[] | null | undefined,
  filter: EngagementFilter
): boolean {
  if (filter === 'all') return true;
  const k = parseEngagementFromSignals(strategicSignals);
  if (filter === 'advisory') return k === 'advisory_only' || k === 'mixed';
  if (filter === 'mixed') return k === 'mixed';
  if (filter === 'supply') return k === 'supply_only';
  return true;
}
