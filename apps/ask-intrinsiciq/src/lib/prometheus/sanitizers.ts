import { cleanPublicList, cleanPublicText } from "@/src/lib/ask-intrinsiciq/presentation";

const FORBIDDEN_PATTERNS: Array<[RegExp, string]> = [
  [/\bPCIM\b/gi, "business intelligence summary"],
  [/\bCIM\b/gi, "company intelligence summary"],
  [/\bartifacts?\b/gi, "source materials"],
  [/\.json\b/gi, ""],
  [/\bJSON\b/gi, "source data"],
  [/source set summaries?/gi, "source summary"],
  [/compact financial inputs/gi, "source summary"],
  [/committee-level output/gi, "public output"],
  [/committee level output/gi, "public output"],
  [/\bsource_artifact\b/gi, "source detail"],
  [/\bsource_item_id\b/gi, "source detail"],
  [/\bevidence_ids?\b/gi, "supporting detail"],
  [/\bevidence_map\b/gi, "supporting detail"],
  [/\buncertainty_missing_data\b/gi, "missing evidence"],
  [/\bdoctrine_id\b/gi, "internal identifier"],
  [/\bnormalized_ids?\b/gi, "internal identifier"],
  [/\boriginal_ids?\b/gi, "internal identifier"],
  [/\bschema\b/gi, "structure"],
  [/\bvalidation\b/gi, "quality check"],
  [/\bdiagnostics\b/gi, "internal notes"],
  [/\bprompt\b/gi, "internal input"],
  [/\bLLM\b/gi, "model"],
  [/\bartifact[_-]contract\b/gi, "internal structure"],
  [/\bpipeline\b/gi, "process"],
  [/\braw artifact\b/gi, "raw source"],
  [/\bsource chunk\b/gi, "source excerpt"],
  [/\binput pack\b/gi, "source package"],
  [/companies\/[^\s]+/gi, "internal source"],
  [/\bev_[a-z0-9_]+\b/gi, "supporting detail"],
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
