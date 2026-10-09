/**
 * PROMETHEUS_LEVEL3_UI_CANARY — feature-flag configuration.
 *
 * All reads are server-side only (Next.js server components / server actions).
 * Defaults to disabled; no canary logic runs unless the flag is explicitly set.
 *
 * Environment variables:
 *   PROMETHEUS_LEVEL3_UI_CANARY_ENABLED   = "true"  (default: "false")
 *   PROMETHEUS_LEVEL3_UI_CANARY_COMPANIES = "sun_pharma,tanla"
 *   PROMETHEUS_LEVEL3_UI_CANARY_QUESTIONS = "how-is-capital-allocated,..."
 *   PROMETHEUS_LEVEL3_UI_CANARY_MATRIX    = "sun_pharma:what-has-management-promised,..."
 *     Exact company:question pairs that are eligible regardless of the flat lists above.
 *     Use when a question is certified for some canary companies but not all.
 */

export type CanaryConfig = {
  enabled: boolean;
  allowedCompanies: ReadonlySet<string>;
  allowedQuestions: ReadonlySet<string>;
  /** Exact "company:question" pairs that bypass the flat-list check. */
  allowedMatrix: ReadonlySet<string>;
};

function parseList(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

export function getCanaryConfig(): CanaryConfig {
  const enabled = process.env.PROMETHEUS_LEVEL3_UI_CANARY_ENABLED === "true";

  const allowedCompanies = new Set(
    parseList(process.env.PROMETHEUS_LEVEL3_UI_CANARY_COMPANIES),
  );

  const allowedQuestions = new Set(
    parseList(process.env.PROMETHEUS_LEVEL3_UI_CANARY_QUESTIONS),
  );

  const allowedMatrix = new Set(
    parseList(process.env.PROMETHEUS_LEVEL3_UI_CANARY_MATRIX),
  );

  return { enabled, allowedCompanies, allowedQuestions, allowedMatrix };
}

export function isCanaryEligible(
  config: CanaryConfig,
  companySlug: string,
  questionId: string,
): boolean {
  if (!config.enabled) return false;
  const matrixKey = `${companySlug}:${questionId}`;
  return (
    config.allowedMatrix.has(matrixKey) ||
    (config.allowedCompanies.has(companySlug) &&
      config.allowedQuestions.has(questionId))
  );
}
