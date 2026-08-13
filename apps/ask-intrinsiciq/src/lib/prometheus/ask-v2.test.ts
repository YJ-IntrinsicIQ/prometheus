import { describe, expect, it } from "vitest";
import { buildAskContextV2 } from "./ask-v2/context-builder";
import { buildAskPlan } from "./ask-v2/router";
import { buildAskResponseV2 } from "./ask-v2/response";
import { buildResearchAnswer, type RawSources } from "./answer-builders";

function makeSources(overrides: Partial<RawSources> = {}): RawSources {
  return {
    pcim: null,
    truthPack: null,
    ownerEarningsBridge: null,
    workingCapitalQuality: null,
    capitalAllocationRoi: null,
    perShareCompounding: null,
    managementCommitments: null,
    projectAssessments: null,
    projectTimelines: null,
    capacityAssessments: null,
    capacityTimelines: null,
    riskAssessments: null,
    riskTimelines: null,
    riskEvolution: null,
    commentaryAssessments: null,
    commentaryTimelines: null,
    commentaryThemes: null,
    managementQualitySummary: null,
    managementQualityDimensions: null,
    capitalAllocationOutcomes: null,
    capitalAllocationTimelines: null,
    promiseTracker: null,
    buffettAnalysis: null,
    grahamAnalysis: null,
    fisherAnalysis: null,
    mungerAnalysis: null,
    lynchAnalysis: null,
    committeeSynthesis: null,
    committeeBriefQa: null,
    panelRunSummary: null,
    rawDiscoveryBundles: null,
    ...overrides,
  };
}

describe("ask v2 router and context", () => {
  it("routes delivery questions to management commitments with progression sources", () => {
    const plan = buildAskPlan("Did management deliver what it promised?");

    expect(plan.primaryIntent).toBe("management_commitments");
    expect(plan.secondaryIntents).toEqual(
      expect.arrayContaining(["projects", "capacity", "management_quality"]),
    );
    expect(plan.requiresProgression).toBe(true);
    expect(plan.canonicalSourceKeys).toEqual(
      expect.arrayContaining(["managementCommitments", "projectAssessments", "capacityAssessments"]),
    );
  });

  it("routes raw disclosure questions to the raw-document fallback path", () => {
    const plan = buildAskPlan("What did management say about export demand in FY22?");

    expect(plan.primaryIntent).toBe("raw_document_fact");
    expect(plan.requiresRawDocumentFallback).toBe(true);
    expect(plan.canonicalSourceKeys).toContain("rawDiscoveryBundles");
  });

  it("builds canonical-first context from management commitments without raw fallback", () => {
    const sources = makeSources({
      managementCommitments: {
        commitments: [
          {
            topic: "Capacity expansion",
            normalized_commitment: "Capacity expansion planned.",
            status: "Delivered",
            delivery_assessment: "Plant commissioned.",
            expected_timeframe: "FY24",
            priority: "High",
          },
        ],
      },
    });

    const context = buildAskContextV2(
      sources,
      buildAskPlan("Did management deliver what it promised?"),
    );

    expect(context.evidence.length).toBeGreaterThan(0);
    expect(context.evidence[0].sourceKey).toBe("managementCommitments");
    expect(context.rawFallbackUsed).toBe(false);
    expect(context.progression.join(" ")).toContain("Capacity expansion");
  });

  it("falls back to raw discovery evidence when canonical detail is missing", () => {
    const sources = makeSources({
      rawDiscoveryBundles: [
        {
          period: "fy22",
          promiseDiscoveries: [
            {
              chunk: "The company expects export demand to improve in the next year.",
              page: 79,
              matched_queries: ["management plans"],
            },
          ],
        },
      ],
    });

    const context = buildAskContextV2(
      sources,
      buildAskPlan("What did management say about export demand in FY22?"),
    );

    expect(context.rawFallbackUsed).toBe(true);
    expect(context.evidence[0].sourceKey).toBe("raw_document_fallback");
    expect(context.evidence[0].detail).toMatch(/export demand/i);
  });
});

describe("ask v2 responses", () => {
  it("returns a v2 answer contract for delivery questions", () => {
    const sources = makeSources({
      managementCommitments: {
        commitments: [
          {
            topic: "Capacity expansion",
            normalized_commitment: "Capacity expansion planned.",
            status: "Delivered",
            delivery_assessment: "Plant commissioned.",
            expected_timeframe: "FY24",
            priority: "High",
          },
        ],
      },
      projectAssessments: {
        assessments: [
          {
            project_name: "New plant",
            execution_summary: "The project moved into operation.",
            observed_business_effect: "Execution credibility strengthened.",
            conviction_impact: "strengthened",
            unresolved_questions: [],
          },
        ],
      },
      capacityAssessments: {
        assessments: [
          {
            capacity_name: "Manufacturing line",
            utilization_status: "operational",
            observed_business_effect: "Capacity is now visible in operations.",
            unresolved_questions: [],
          },
        ],
      },
    });

    const answer = buildResearchAnswer("datapatterns", "did-past-claims-come-true", sources, null);

    expect(answer).not.toBeNull();
    expect(answer?.directAnswer).toMatch(/delivered|promises/i);
    expect(answer?.conclusion).toBeDefined();
    expect(answer?.whatChanged).toBeDefined();
    expect(answer?.confidence).toBeDefined();
    expect(answer?.askDiagnostics?.detectedIntent).toBe("management_commitments");
    expect(answer?.askDiagnostics?.validationStatus).toBe("pass");
  });

  it("builds a free-text v2 response for a raw management question", () => {
    const sources = makeSources({
      rawDiscoveryBundles: [
        {
          period: "fy22",
          promiseDiscoveries: [
            {
              chunk: "The company expects export demand to improve in the next year.",
              page: 79,
              matched_queries: ["management plans"],
            },
          ],
        },
      ],
    });

    const response = buildAskResponseV2(
      "What did management say about export demand in FY22?",
      sources,
    );

    expect(response.plan.primaryIntent).toBe("raw_document_fact");
    expect(response.context.rawFallbackUsed).toBe(true);
    expect(response.conclusion).toMatch(/export demand/i);
    expect(response.validationIssues).toEqual([]);
  });

  it("cleans malformed investor-lens text and placeholder uncertainty after the final gate", () => {
    const sources = makeSources({
      buffettAnalysis: {
        assessment: {
          overall_view: "described as weak in;",
        },
        key_findings: [
          "Business model: defence and space systems integration with vertical manufacturing goals.",
          "Returns remain mixed.",
        ],
        red_flags: [
          "source set summaries",
          "compact financial inputs",
        ],
        open_uncertainties: [
          "Uncertainty note: unspecified",
        ],
      },
      committeeSynthesis: {
        overall_committee_view: {
          summary: "Buffett should focus on owner earnings.",
        },
      },
    });

    const answer = buildResearchAnswer("datapatterns", "what-would-buffett-focus-on", sources, null);

    expect(answer).not.toBeNull();
    expect(answer?.directAnswer.endsWith(";")).toBe(false);
    expect(JSON.stringify(answer)).not.toContain("source set summaries");
    expect(JSON.stringify(answer)).not.toContain("unspecified");
    expect(JSON.stringify(answer)).not.toContain("compact financial inputs");
  });
});
