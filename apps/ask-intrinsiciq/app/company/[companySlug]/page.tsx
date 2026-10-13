import { notFound } from "next/navigation";
import { AppFrame } from "@/src/components/layout/app-frame";
import { StoryView } from "@/src/components/story/story-view";
import { loadExplorer } from "@/src/lib/catalog/load-explorer";
import { loadStory } from "@/src/lib/story/load-story";

// The Investment Cockpit: Story, Connections, Discoveries and the five investor questions for one company.
// Read per request so an approval change applies at once.
export const dynamic = "force-dynamic";

export default async function CompanyPage({ params }: { params: Promise<{ companySlug: string }> }) {
  const { companySlug } = await params;
  const [story, explorer] = await Promise.all([loadStory(companySlug), loadExplorer(companySlug)]);
  if (!story) notFound();
  return (
    <AppFrame>
      <StoryView story={story} journey={explorer?.stages} />
    </AppFrame>
  );
}
