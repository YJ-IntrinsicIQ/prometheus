import { loadCatalog } from "@/src/lib/catalog/catalog";
import { loadApprovedAnswers } from "@/src/lib/story/approved-answers";
import { COMPANIES } from "@/src/lib/story/companies";
import { loadQuestionView } from "@/src/lib/story/load-question";
import { loadStoryInputs } from "@/src/lib/story/load-story";
import { buildStory } from "@/src/lib/story/story-adapter";
import { loadAbsenceLedger, withAbsence } from "@/src/lib/provenance/absence";
import { buildPanel, type Panel } from "./build-panel";
import { loadPanelData } from "./data";

// Read-only. Composes the Panel from what already exists: approved answers, the Story's records and canonical
// financial records. Nothing is written, generated or approved here.
export async function loadPanel(slug: string): Promise<Panel | null> {
  if (!COMPANIES[slug]) return null;
  const [inputs, data, answers, catalog] = await Promise.all([loadStoryInputs(slug), loadPanelData(slug), loadApprovedAnswers(slug), loadCatalog()]);
  if (!inputs || !data) return null;
  const notices = (await Promise.all(Object.keys(answers).map((q) => loadQuestionView(slug, q)))).flatMap((v) => (v?.notices ?? []).map((n) => ({ title: n.title, text: n.text })));
  const panel = buildPanel({ slug, company: COMPANIES[slug].name, data, story: buildStory(inputs), inputs, answers, catalog, notices });
  const ledger = await loadAbsenceLedger(slug);
  return { ...panel, specialists: panel.specialists.map((s) => withAbsence(s, ledger)) };
}
