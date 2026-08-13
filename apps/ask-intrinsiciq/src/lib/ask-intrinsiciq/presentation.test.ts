import { describe, expect, it } from "vitest";
import {
  prepareFlowLabelForDisplay,
  prepareFlowStepForDisplay,
  prepareLensBulletForDisplay,
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
