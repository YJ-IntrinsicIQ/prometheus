// Capital-allocation facts read from the economic-attribution cases (which carry the ledger's periods and amounts).
import { cr, fyLabel } from "./text";

type Obj = Record<string, unknown>;
const periods = (c: Obj) => ((c.deployment_periods as string[] | undefined) ?? []);

export function dealName(d: Obj): string | undefined {
  const desc = String(d.action_description);
  const proposed = /^Proposed acquisition of\s+(.+?)\s*\(/i.exec(desc)?.[1]?.trim();
  if (proposed) return proposed;
  if (/\b(sale|sold|divest|disposal)\b/i.test(desc)) return undefined;
  const direct = /^Acquisition\s*\(([^)]+)\)/i.exec(desc)?.[1]?.trim();
  if (direct) return direct;
  if (!/acqui|incorporat/i.test(desc) || /fixed assets|property|plant|equipment|intangible|software|vehicle/i.test(desc)) return undefined;
  return (/(?:shareholding|stake|interest)\s+in\s+(.+?)(?:\s*\(|$)/i.exec(desc) ?? /\bof\s+(.+?)(?:\s*\(|$)/i.exec(desc))?.[1]?.trim();
}

export function dealAmount(d: Obj): number | null {
  const n = typeof d.amount_inr_cr === "number" ? d.amount_inr_cr : Number(/₹\s*~?([\d,.]+)\s*Cr/i.exec(String(d.investor_interpretation))?.[1]?.replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : null;
}

const completed = (c: Obj) => c.action_type === "acquisition" && c.deployment_state === "COMPLETED_TRANSACTION" && periods(c).length > 0;
export const completedDeals = (cases: Obj[]) => cases.filter((x) => completed(x) && dealName(x));
/** Acquisitions the filing signs/announces but does not complete (ledger transaction_status). Signed is not completed. */
export const pendingDeals = (cases: Obj[]) =>
  cases.filter((x) => x.action_type === "acquisition" && (x.transaction_status === "signed_pending_completion" || x.transaction_status === "announced") && dealName(x));
export const divestments = (cases: Obj[]) =>
  cases.filter((x) => completed(x) && /\b(sale|sold|divest|disposal)\b/i.test(String(x.action_description)) && /shareholding|stake|subsidiary|business/i.test(String(x.action_description)));

/** The organic-capex ledger line with an amount spread over several years (one per company). */
export function capexProgramme(cases: Obj[]): { amount: number; first: number; last: number; label: string; span: string } | null {
  const c = cases
    .filter((x) => x.action_type === "organic_capex" && x.deployment_state === "DEPLOYED" && typeof x.amount_inr_cr === "number" && (x.amount_inr_cr as number) > 0 && periods(x).length >= 2)
    .sort((a, b) => (b.amount_inr_cr as number) - (a.amount_inr_cr as number))[0];
  if (!c) return null;
  // The amount belongs to ONE period (amount_period, from the ledger). Only older artifacts lack it; they keep the span label.
  const own = typeof c.amount_period === "string" ? Number(/\d+/.exec(c.amount_period)?.[0]) : NaN;
  if (Number.isFinite(own)) return { amount: c.amount_inr_cr as number, first: own, last: own, label: `${cr(c.amount_inr_cr as number)} in ${fyLabel(`fy${own}`)}`, span: fyLabel(`fy${own}`) };
  const ys = periods(c).map((p) => Number(/\d+/.exec(p)?.[0])).sort((a, b) => a - b);
  return { amount: c.amount_inr_cr as number, first: ys[0], last: ys[ys.length - 1], label: `${cr(c.amount_inr_cr as number)} across ${fyLabel(`fy${ys[0]}`)}–${fyLabel(`fy${ys[ys.length - 1]}`)}`, span: `${fyLabel(`fy${ys[0]}`)}–${fyLabel(`fy${ys[ys.length - 1]}`)}` };
}
