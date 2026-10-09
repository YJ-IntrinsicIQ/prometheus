import { describe, expect, it } from "vitest";
import {
  prepareFlowLabelForDisplay,
  prepareFlowStepForDisplay,
  prepareLensBulletForDisplay,
  cleanPublicList,
  cleanPublicText,
} from "@/src/lib/ask-intrinsiciq/presentation";

describe("presentation helpers", () => {
  it("removes investor-lens prefixes and compacts long bullets", () => {
    const output = prepareLensBulletForDisplay(
      "Business model: designs, qualifies and manufactures high-reliability electronic systems for MoD and ISRO programmes with formal qualifications and vertical integration.",
    );

    expect(output.startsWith("designs, qualifies and manufactures")).toBe(true);
    expect(output.includes("Business model:")).toBe(false);
    expect(output.split(/\s+/).length).toBeLessThanOrEqual(24);
  });

  it("keeps revenue-flow labels compact", () => {
    expect(prepareFlowLabelForDisplay("Win programme or order")).toBe(
      "Win programme order",
    );
    expect(prepareFlowLabelForDisplay("Bill against milestones")).toBe(
      "Bill milestones",
    );
  });

  it("keeps revenue-flow explanations short enough for compact nodes", () => {
    const output = prepareFlowStepForDisplay(
      "The company then appears to tailor the subsystem, product, or integrated system to programme requirements.",
    );

    expect(output.includes("The company then appears to")).toBe(false);
    expect(output.split(/\s+/).length).toBeLessThanOrEqual(22);
  });

  it("does not collapse spaces inside revenue-flow copy", () => {
    const linked = prepareFlowStepForDisplay(
      "Billing appears linked to delivery acceptance or project milestones rather than simple subscription timing.",
    );
    const lag = prepareFlowStepForDisplay(
      "Cash conversion can lag delivery because collections depend on programme timing and working-capital intensity.",
    );

    expect(linked.toLowerCase()).not.toContain("appearslinked");
    expect(lag.toLowerCase()).not.toContain("canlag");
  });

  it("drops malformed public fragments with dangling prepositions before semicolons", () => {
    expect(
      cleanPublicText(
        "Management quality / capital-allocation discipline described as weak in; execution commitments have unproven delivery in later-year evidence.",
      ),
    ).toBe("");
  });
});

// ── ENG-155: key_point dedup against rendered vs. unrendered fields ──────────
// Root cause: interpretation.whatChanged was being added to the `seen` set in
// answer-view.tsx despite never being rendered in InvestorAnswerStack. This
// caused key_points matching whatChanged to be near-deduped away, making them
// invisible to investors.
describe("ENG-155 – cleanPublicList dedup: rendered vs. unrendered field suppression", () => {
  // Simulates the revenue-predictability / churn / margin promise text structure.
  const platformEconomicsKP =
    "FY22: Expectations of continued momentum from the platform approach with benefits such as higher revenue predictability, lower customer churn and healthier gross margin.";
  const aiMessagingKP =
    "FY24: Use of AI and new messaging platforms has driven measurable operational improvements, including a 90% reduction in registration process time and a 60–80% reduction in complaints per million SMS.";
  const customerObsessionKP =
    "FY22: Fostering a culture of customer obsession that keeps the voice of the customer at the center of all decisions.";

  it("a key_point identical to an item in seen is suppressed by cleanPublicList", () => {
    const seen = new Set<string>();
    // Populate seen as if whatChanged contained this text (the old broken behaviour)
    cleanPublicList([platformEconomicsKP], { seen });
    // Now the key_point cannot get through — it is near-identical to the seen item
    const result = cleanPublicList([platformEconomicsKP, aiMessagingKP], { seen });
    expect(result).not.toContain(platformEconomicsKP);
    expect(result).toContain(aiMessagingKP);
  });

  it("a key_point absent from seen survives cleanPublicList regardless of other suppressions", () => {
    const seen = new Set<string>();
    // Populate seen only with items that do NOT overlap the platform-economics KP
    cleanPublicList([customerObsessionKP], { seen });
    const result = cleanPublicList([platformEconomicsKP, aiMessagingKP], { seen });
    // Platform-economics key_point must be included when not in seen
    expect(result).toContain(platformEconomicsKP);
    expect(result).toContain(aiMessagingKP);
  });

  it("key_point near-dup of evidenceSummary is suppressed (it is rendered in EvidenceDisclosure)", () => {
    const seen = new Set<string>();
    // evidenceSummary items populate seen in answer-view.tsx — these ARE rendered
    cleanPublicList([customerObsessionKP], { seen });
    const result = cleanPublicList([customerObsessionKP, platformEconomicsKP], { seen });
    expect(result).not.toContain(customerObsessionKP);
    expect(result).toContain(platformEconomicsKP);
  });

  it("an empty key_points list produces an empty result", () => {
    const result = cleanPublicList([], { seen: new Set(), limit: 4 });
    expect(result).toHaveLength(0);
  });

  it("limit=4 caps the output even when more items pass the dedup check", () => {
    const items = [
      "Alpha management committed to expanding the distribution network across tier-two cities by FY24.",
      "Beta management committed to reducing debt-to-equity ratio to below one times by FY25.",
      "Gamma management committed to increasing the share of premium products from ten to thirty percent.",
      "Delta management committed to maintaining working-capital cycle below sixty days by FY26.",
      "Epsilon management committed to achieving twenty percent revenue from international markets.",
    ];
    const result = cleanPublicList(items, { seen: new Set(), limit: 4 });
    expect(result.length).toBeLessThanOrEqual(4);
  });
});
