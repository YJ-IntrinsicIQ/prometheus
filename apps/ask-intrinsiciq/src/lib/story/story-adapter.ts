import { buildAccountability, type Accountability } from "./accountability";
import { buildConnections, type Connection } from "./connections";
import { buildDiscoveries, type Discovery } from "./discoveries";
import { registerSourceOf, type CommitmentRow } from "./commitment-evidence";
import { commitmentEvents, investmentEvents, outcomeEvents, registerCommitmentEvents, riskEvents, strategyEvents, type RawEvent, type Series, type StoryCategory, type StoryKind } from "./story-events";
import { clean, firstSentence, fyLabel, fyNum } from "./text";

// Presentation adapter for "The Story". It reads existing records and reshapes them for display; it never
// generates conclusions: every sentence is either a stored string (cleaned of internal IDs) or a fixed, hedged
// template that states what a record type means. Approved records only.
export { clean, fyNum };
export type { StoryCategory, StoryKind };

export type StoryEvent = Omit<RawEvent, "related" | "key"> & {
  id: string;
  initial: boolean;
  related: { id: string; label: string; note: string }[]; // only where records tie the two events together
};

export type Story = {
  company: string;
  slug: string;
  available: string[]; // investor questions with an approved answer
  docs: string[]; // fiscal years whose annual report can be opened
  titles?: Record<string, string>; // titles of the approved questions, for related-question links
  cutoff: string | null;
  events: StoryEvent[];
  gaps: string[];
  sources: string[];
  commitments?: CommitmentRow[];
  accountability?: Accountability;
  connections: Connection[];
  discoveries: Discovery[];
};

type Obj = Record<string, unknown>;
export type StoryInputs = {
  slug: string;
  key: string;
  company: string;
  latestYear: number;
  commitments: Obj[];
  projects: Obj[];
  attribution: Obj[];
  riskThemes: Obj[]; // gold risk-evolution themes: the same source as the approved risk answer
  strategyThemes: Obj[]; // gold strategy-evolution themes
  revenue: Series;
  pat: Series;
  commitmentRows: CommitmentRow[]; // from the approved promise/delivery answers, when they carry reconciled evidence
  docs: string[];
  available: string[]; // question ids whose answer passes the approval gate; others are never linked
  titles?: Record<string, string>; // titles of exactly those questions
  withholdCommitments: boolean; // register-based commitment views are not shown (see companies.ts)
};

const MAX_EVENTS = 22, PER_CATEGORY = 7, MAX_INITIAL = 8, INITIAL_PER_CATEGORY = 3;
const INTERP = {
  statement: "A stated target gives investors a benchmark to check against later reports.",
  project: "A facility in operation is a precondition for output, not proof of returns.",
};

function coreAndProjectEvents(input: StoryInputs, sameTopic: (text: string) => boolean): RawEvent[] {
  const raw: RawEvent[] = [];
  for (const m of input.commitments) {
    const sq = m.semantic_quality as Obj | undefined;
    if (sq?.investor_relevance !== "core") continue;
    const refs = (m.source_references as Obj[] | undefined) ?? [];
    const period = String(m.announcement_period ?? refs[0]?.period ?? "");
    const stmt = clean(String(m.original_statement ?? ""));
    if (sameTopic(stmt)) continue;
    raw.push({
      key: `core-${raw.length}`, period: fyLabel(period), sortKey: fyNum(period) ?? 0, category: "Strategy", kind: "Management statement",
      headline: firstSentence(stmt, 140), summary: firstSentence(stmt), original: stmt,
      interpretation: { happened: `In ${fyLabel(period)}, management stated: ${stmt}`, matters: INTERP.statement, unproven: "There is not enough later evidence in the records to judge whether this was carried out." },
      evidence: [`Annual report ${fyLabel(period)}, p.${refs[0]?.page ?? "n/a"}`],
      limitations: ["Stated intention only; no delivery record is attached."],
      priority: 3,
    });
  }
  for (const p of input.projects) {
    const a = p.assessment as Obj | undefined;
    const name = String(p.project_name ?? "");
    if (a?.execution_status !== "operational" || name.length < 12) continue;
    const ref = ((p.source_references as Obj[] | undefined) ?? [])[0] ?? {};
    const unresolved = ((a?.unresolved_questions as string[] | undefined) ?? [])[0];
    raw.push({
      key: `project-${raw.length}`, period: fyLabel(String(ref.period ?? a?.period ?? "")), sortKey: fyNum(String(ref.period ?? a?.period ?? "")) ?? 0, category: "Execution", kind: "Confirmed activity",
      headline: name.length > 110 ? (name.split(" (")[0].length >= 20 ? name.split(" (")[0] : firstSentence(name, 140)) : name,
      ...(name.length > 110 ? { original: name } : {}),
      summary: "Reported as operational in the annual report.",
      interpretation: { happened: `${name} is reported as operational.`, matters: INTERP.project, unproven: unresolved ? clean(unresolved) : "Cost, timeline and returns are not shown in the records." },
      evidence: [`Annual report ${fyLabel(String(ref.period ?? ""))}, p.${ref.page ?? "n/a"}`],
      limitations: unresolved ? [clean(unresolved)] : [],
      priority: 2,
    });
  }
  const recent = (xs: RawEvent[]) => [...xs].sort((a, b) => b.sortKey - a.sortKey).slice(0, 3);
  return [...recent(raw.filter((e) => e.key.startsWith("core"))), ...recent(raw.filter((e) => e.key.startsWith("project")))];
}

export function buildStory(input: StoryInputs): Story {
  const latestRevenue = [...input.revenue].reverse().find((p) => Number.isFinite(p.value))?.value ?? null;
  const commitmentRaw = input.commitmentRows.length
    ? commitmentEvents(input.commitmentRows, registerSourceOf(input.commitments))
    : input.withholdCommitments ? [] : registerCommitmentEvents(input.commitments, input.latestYear);
  const words = (t: string) => new Set(t.toLowerCase().replace(/™/g, "").match(/[a-z]{5,}/g) ?? []);
  const coveredWords = commitmentRaw.filter((e) => e.headline.startsWith("Commitment:")).map((e) => words(e.headline));
  const sameTopic = (t: string) => coveredWords.some((w) => [...words(t)].filter((x) => w.has(x)).length >= 3);
  const raw: RawEvent[] = [
    ...commitmentRaw,
    ...strategyEvents(input.strategyThemes),
    ...investmentEvents(input.attribution, latestRevenue),
    ...outcomeEvents(input.revenue, input.pat),
    ...riskEvents(input.riskThemes),
    ...coreAndProjectEvents(input, sameTopic),
  ];

  // Important developments over event count: the highest-priority events, with no category crowding out the rest.
  const perCat = new Map<StoryCategory, number>();
  const kept = [...raw].sort((a, b) => b.priority - a.priority || a.sortKey - b.sortKey).filter((e) => {
    const n = perCat.get(e.category) ?? 0;
    if (n >= PER_CATEGORY) return false;
    perCat.set(e.category, n + 1);
    return true;
  }).slice(0, MAX_EVENTS);
  const ordered = kept.sort((a, b) => a.sortKey - b.sortKey || b.priority - a.priority);
  const ids = new Map(ordered.map((e, i) => [e.key, `event-${i + 1}`]));

  const initial = new Set<string>();
  const earliest = ordered.find((e) => e.category === "Strategy");
  if (earliest) initial.add(earliest.key);
  const shown = new Map<StoryCategory, number>();
  if (earliest) shown.set(earliest.category, 1);
  for (const e of [...ordered].sort((a, b) => b.priority - a.priority || a.sortKey - b.sortKey)) {
    if (initial.size >= MAX_INITIAL) break;
    if ((shown.get(e.category) ?? 0) >= INITIAL_PER_CATEGORY || initial.has(e.key)) continue;
    initial.add(e.key);
    shown.set(e.category, (shown.get(e.category) ?? 0) + 1);
  }
  const byKey = new Map(ordered.map((e) => [e.key, e]));
  // A tie is mutual: if one event points at another, the other points back.
  const ties = new Map<string, { key: string; note: string }[]>(ordered.map((e) => [e.key, [...(e.related ?? [])]]));
  for (const e of ordered) for (const r of e.related ?? []) if (byKey.has(r.key) && !ties.get(r.key)!.some((x) => x.key === e.key)) ties.get(r.key)!.push({ key: e.key, note: r.note });
  const events: StoryEvent[] = ordered.map(({ key, related: _related, ...e }) => ({
    ...e,
    id: ids.get(key)!,
    initial: initial.has(key),
    related: (ties.get(key) ?? []).filter((r) => ids.has(r.key)).map((r) => ({ id: ids.get(r.key)!, label: `${byKey.get(r.key)!.period}: ${byKey.get(r.key)!.headline}`, note: r.note })),
  }));

  const cutoffYear = Math.max(0, ...events.map((e) => Math.floor(e.sortKey)).filter((y) => y > 0 && y <= input.latestYear));
  return {
    company: input.company,
    slug: input.slug,
    available: input.available,
    titles: input.titles,
    docs: input.docs,
    commitments: input.commitmentRows.length ? input.commitmentRows : undefined,
    accountability: input.withholdCommitments ? undefined : buildAccountability(input),
    connections: buildConnections(input),
    discoveries: buildDiscoveries(input),
    cutoff: cutoffYear ? `Evidence through the FY${cutoffYear} annual report` : null,
    events,
    gaps: events.length ? [] : ["No story events could be built from the available records."],
    sources: ["Management commitments register", "Approved answers", "Strategy evolution record", "Capital-allocation ledger", "Financial statements", "Risk evolution timeline", "Projects registry"],
  };
}
