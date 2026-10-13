// Generic challenge engine: evaluates declarative checks against the TEXT of rendered investor surfaces.
// No company logic lives here; companies, figures and patterns are fixture data in tests/challenge/cases.json.
import type { Surface } from "./surfaces";

export type Check =
  | { type: "present" | "absent"; pattern: string; scope?: string[]; note?: string }
  | { type: "present_near" | "absent_near"; a: string; b: string; window: number; note?: string }
  | { type: "requires_when"; when: string; then: string; window: number; note?: string }
  | { type: "label_conflict"; figure: string; label: string; window: number; note?: string }
  | { type: "not_both"; a: string; b: string; note?: string }
  | { type: "single_valued"; pattern: string; note?: string };

export type Case = {
  id: string; pri: string; company: string; companies?: string[]; class: string; predicted: "PASS" | "FAIL"; control?: boolean;
  expected: string; source: Record<string, unknown>[]; checks: Check[];
};
export type CheckResult = { ok: boolean; company: string; check: string; evidence: string };

const re = (p: string, f = "gi") => new RegExp(p, f);
const clip = (s: string, n = 170) => s.replace(/\s+/g, " ").trim().slice(0, n);
const inScope = (name: string, scope?: string[]) => !scope || scope.some((g) => name === g || (g.endsWith("*") && name.startsWith(g.slice(0, -1))));
const snippet = (t: string, i: number, len: number) => clip(t.slice(Math.max(0, i - 50), i + len + 50));

export function runCheck(c: Check, surfaces: Surface[], company: string): CheckResult {
  const S = (sc?: string[]) => surfaces.filter((s) => inScope(s.name, sc));
  const label = `${c.type}${"pattern" in c ? ` /${c.pattern}/` : ""}${c.note ? ` — ${c.note}` : ""}`;
  const res = (ok: boolean, evidence: string): CheckResult => ({ ok, company, check: label, evidence });
  switch (c.type) {
    case "present": {
      for (const s of S(c.scope)) { const m = re(c.pattern).exec(s.text); if (m) return res(true, `[${s.name}] ${snippet(s.text, m.index, m[0].length)}`); }
      return res(false, `no match in ${S(c.scope).length} surfaces`);
    }
    case "absent": {
      for (const s of S(c.scope)) { const m = re(c.pattern).exec(s.text); if (m) return res(false, `[${s.name}] ${snippet(s.text, m.index, m[0].length)}`); }
      return res(true, `no match in ${S(c.scope).length} surfaces`);
    }
    case "present_near":
    case "absent_near": {
      for (const s of surfaces) {
        for (const m of s.text.matchAll(re(c.a))) {
          const i = m.index!; const win = s.text.slice(Math.max(0, i - c.window), i + m[0].length + c.window);
          if (re(c.b).test(win)) return res(c.type === "present_near", `[${s.name}] ${snippet(s.text, i, m[0].length + 40)}`);
        }
      }
      return res(c.type === "absent_near", `"${c.a}" never within ${c.window} chars of "${c.b}"`);
    }
    case "requires_when": {
      let seen = 0;
      for (const s of surfaces) for (const m of s.text.matchAll(re(c.when))) {
        seen++; const i = m.index!;
        if (!re(c.then).test(s.text.slice(Math.max(0, i - c.window), i + m[0].length + c.window))) return res(false, `[${s.name}] ${snippet(s.text, i, m[0].length)} — no "${c.then}" within ${c.window}`);
      }
      return res(seen > 0, seen ? `${seen} occurrences all carry context` : `trigger never occurs`);
    }
    case "label_conflict": {
      const labels = new Map<string, string>();
      for (const s of surfaces) for (const m of s.text.matchAll(re(c.figure))) {
        const i = m.index! + m[0].length;
        const after = re(c.label).exec(s.text.slice(i, i + c.window));
        const before = [...s.text.slice(Math.max(0, m.index! - c.window), m.index!).matchAll(re(c.label))].pop();
        const l = (after ?? before)?.[0]; if (l) labels.set(l, `[${s.name}]`);
      }
      return res(labels.size <= 1, `labels for ${c.figure}: ${[...labels].map(([l, w]) => `${l} ${w}`).join("; ") || "none"}`);
    }
    case "not_both": {
      const a = surfaces.find((s) => re(c.a).test(s.text)), b = surfaces.find((s) => re(c.b).test(s.text));
      return res(!(a && b), a && b ? `"${c.a}" in [${a.name}] but "${c.b}" in [${b.name}]` : "no contradiction");
    }
    case "single_valued": {
      const vals = new Map<string, string>();
      for (const s of surfaces) for (const m of s.text.matchAll(re(c.pattern))) if (!vals.has(m[1])) vals.set(m[1], `[${s.name}] ${clip(m[0], 60)}`);
      return res(vals.size <= 1, `values: ${[...vals].map(([v, w]) => `${v} ${w}`).join("; ") || "none"}`);
    }
  }
}

/** A case passes only if every check passes for every company it names. */
export function runCase(c: Case, surfacesBy: Record<string, Surface[]>) {
  const results = (c.companies ?? [c.company]).flatMap((co) => c.checks.map((k) => runCheck(k, surfacesBy[co] ?? [], co)));
  return { id: c.id, status: results.every((r) => r.ok) ? ("PASS" as const) : ("FAIL" as const), results };
}
