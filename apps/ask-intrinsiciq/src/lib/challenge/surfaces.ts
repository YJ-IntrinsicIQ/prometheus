// Renders every investor-visible surface for a company through the REAL loaders (no JSON shortcuts) and flattens each to text.
import { loadExplorer } from "@/src/lib/catalog/load-explorer";
import { loadPanel } from "@/src/lib/panel/load-panel";
import { loadApprovedAnswers } from "@/src/lib/story/approved-answers";
import { loadQuestionView } from "@/src/lib/story/load-question";
import { loadStory } from "@/src/lib/story/load-story";

export type Surface = { name: string; text: string };

/** Every string an investor can read inside a loader result (routes/ids are skipped). */
export function strings(v: unknown, out: string[] = []): string[] {
  if (typeof v === "string") { if (/\s|\d/.test(v) && !v.startsWith("/")) out.push(v); }
  else if (Array.isArray(v)) v.forEach((x) => strings(x, out));
  else if (v && typeof v === "object") Object.values(v).forEach((x) => strings(x, out));
  return out;
}

export async function renderSurfaces(slug: string): Promise<Surface[]> {
  const out: Surface[] = [];
  const add = (name: string, v: unknown) => v && out.push({ name, text: strings(v).join("\n") });
  for (const q of Object.keys(await loadApprovedAnswers(slug))) add(`question:${q}`, await loadQuestionView(slug, q));
  add("story", await loadStory(slug));
  const panel = await loadPanel(slug);
  for (const s of panel?.specialists ?? []) add(`panel:${(s as { id: string }).id}`, s);
  add("explorer", await loadExplorer(slug));
  return out;
}
