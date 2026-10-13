import { cleanPublicList, cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";

// No /g flag: global regexes keep lastIndex between .test() calls, which made results depend on call order.
const FORBIDDEN_PATTERNS: Array<[RegExp, string]> = [
  [/\bPCIM\b/i, "business intelligence summary"],
  [/\bCIM\b/i, "company intelligence summary"],
  [/\bartifacts?\b/i, "source materials"],
  [/\.json\b/i, ""],
  [/\bJSON\b/i, "source data"],
  [/source set summaries?/i, "source summary"],
  [/compact financial inputs/i, "source summary"],
  [/committee-level output/i, "public output"],
  [/committee level output/i, "public output"],
  [/\bsource_artifact\b/i, "source detail"],
  [/\bsource_item_id\b/i, "source detail"],
  [/\bevidence_ids?\b/i, "supporting detail"],
  [/\bevidence_map\b/i, "supporting detail"],
  [/\buncertainty_missing_data\b/i, "missing evidence"],
  [/\bdoctrine_id\b/i, "internal identifier"],
  [/\bnormalized_ids?\b/i, "internal identifier"],
  [/\boriginal_ids?\b/i, "internal identifier"],
  [/\bschema\b/i, "structure"],
  // Regulatory milestone wording is allowed: "EMA validation" and the exact Nidlegy phrase "validation dated June 2024 and June 3, 2025".
  [/(?<!EMA )\bvalidation\b(?! dated June 2024 and June 3, 2025)/i, "quality check"],
  [/\bdiagnostics\b/i, "internal notes"],
  [/\bprompt\b/i, "internal input"],
  [/\bLLM\b/i, "model"],
  [/\bartifact[_-]contract\b/i, "internal structure"],
  [/\b(?:data|ingestion|ML|AI|LLM|ETL|CI|CD|deployment|processing|training|inference|feature|extraction|scoring)\s+pipeline\b/i, "process"],
  [/\braw artifact\b/i, "raw source"],
  [/\bsource chunk\b/i, "source excerpt"],
  [/\binput pack\b/i, "source package"],
  [/companies\/[^\s]+/i, "internal source"],
  [/\bev_[a-z0-9_]+\b/i, "supporting detail"],
];

export function sanitizeUiText(value: string | null | undefined) {
  return cleanPublicText(value ?? "");
}

export function sanitizeUiList(values: Array<string | null | undefined>) {
  return cleanPublicList(values.map((value) => sanitizeUiText(value)));
}

export function containsForbiddenUiTerm(value: string) {
  return FORBIDDEN_PATTERNS.some(([pattern]) => pattern.test(value));
}
