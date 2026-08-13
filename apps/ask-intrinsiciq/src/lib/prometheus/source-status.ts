export type SourceStatus = {
  available: string[];
  missing: string[];
};

export function buildDevelopmentNote(sourceStatus: SourceStatus) {
  if (process.env.NODE_ENV === "production" || sourceStatus.missing.length === 0) {
    return null;
  }

  return "Using fallback demo content for some sections because not all source materials are available in this environment.";
}
