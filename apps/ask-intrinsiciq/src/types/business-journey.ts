import type { EvidenceStatus } from "@/src/types/evidence";

export type BusinessJourneyStage = {
  id: string;
  periodLabel: string;
  title: string;
  simpleDescription: string;
  significance: string;
  evidenceStatus: EvidenceStatus;
  displayOrder: number;
};

export type BusinessJourney = {
  summary: string;
  stages: BusinessJourneyStage[];
  currentDirection: string;
  openQuestions: string[];
};
